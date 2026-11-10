# -*- coding: utf-8 -*-
"""补充源：中公教育「广东教师招聘 · 招聘公告」列表（gd.offcn.com）

为什么加这个源：
  学校官网 / 教育局官网只覆盖一部分学校，很多幼儿园、民办校、高职院校的
  招聘公告只发在公众号或区级子页面，我们的官方源抓不到。中公把全省教师
  招聘公告按 21 个城市汇总转载，每条详情页抬头都写着「来源：XX人民政府 /
  XX教育局」，我们照抄这个来源单位，页面上标注「XX（中公教育转载）」。

用法：
    python crawler/offcn.py

输出：
    合并进 crawler/data_anns.js（按 sourceUrl 去重，不动已有数据）。
    必须在 crawler.py 之后跑（crawler.py 会覆盖写整个文件）。
"""
import os
import re
import sys
import json
import time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from crawler import (fetch, soup_of, find_date, _extract_deadline,
                     _deadline_from_title, _guess_est, _stage_of,
                     _extract_targets, _extract_positions, _extract_conditions,
                     _extract_process, _extract_signup, _extract_contact)

OUT_FILE = os.path.join(BASE_DIR, "data_anns.js")

# 21 个地级市，顺序跟网站一致
CITY_SLUGS = [
    ("guangzhou", "广州"), ("shaoguan", "韶关"), ("shenzhen", "深圳"),
    ("zhuhai", "珠海"), ("shantou", "汕头"), ("foshan", "佛山"),
    ("jiangmen", "江门"), ("zhanjiang", "湛江"), ("maoming", "茂名"),
    ("zhaoqing", "肇庆"), ("huizhou", "惠州"), ("meizhou", "梅州"),
    ("shanwei", "汕尾"), ("heyuan", "河源"), ("yangjiang", "阳江"),
    ("qingyuan", "清远"), ("dongguan", "东莞"), ("zhongshan", "中山"),
    ("chaozhou", "潮州"), ("jieyang", "揭阳"), ("yunfu", "云浮"),
]

LIST_TPL = "http://gd.offcn.com/html/jiaoshi/zhaokaoxinxi/zpgg/%s/"
MAX_PAGES = 3      # 每个城市最多翻 3 页
KEEP_DAYS = 90     # 只收 90 天内的公告，太老的没必要

# 只要「招聘」类，不要成绩/面试/公示这些流程公告
SKIP_WORDS = ("拟录用", "拟聘用", "拟聘", "公示", "成绩", "面试名单", "体检",
              "准考证", "资格复审", "报名情况", "考察", "递补", "录用名单",
              # 下面这些虽然也「招人」，但不是教师岗，混进来会拉低网站垂直度
              "基层公共就业创业服务", "公益性岗位", "社区工作者", "辅警",
              "协管员", "网格员", "专职消防", "后备干部", "选调生", "三支一扶",
              "村官", "事业单位人员", "编外人员招聘")
KEEP_WORDS = ("招聘", "招录", "选聘", "诚聘", "招募", "引进")


def log(msg):
    print(msg, flush=True)


def parse_list(html):
    """从中公列表页提取 (日期, 标题, 链接)"""
    items = []
    for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.S):
        body = m.group(1)
        dm = re.search(r"<span>\s*(20\d{2}-\d{2}-\d{2})\s*</span>", body)
        if not dm:
            continue
        am = re.search(r'href="([^"]*?/html/\d{4}/\d{2}/\d+\.html)"[^>]*?title="([^"]+)"', body)
        if not am:
            continue
        url = am.group(1)
        if url.startswith("/"):
            url = "https://gd.offcn.com" + url
        elif not url.startswith("http"):
            url = "https://gd.offcn.com" + url
        items.append((dm.group(1), am.group(2).strip(), url))
    return items


def want(title):
    """判断是不是「招聘」类公告"""
    if not any(k in title for k in KEEP_WORDS):
        return False
    if any(k in title for k in SKIP_WORDS):
        return False
    return True


def extract_school(title):
    """从标题里抠学校名，例：
    「2026年11月广东广州市第一一三中学陶育实验学校招聘编外聘用制专任教师1人公告」
    → 广州市第一一三中学陶育实验学校
    """
    t = title
    t = re.sub(r"^20\d{2}\s*(年|年度|下半年|上半年)?\s*", "", t)
    t = re.sub(r"^\d{1,2}\s*月", "", t)
    t = re.sub(r"^广东(省)?", "", t)
    t = re.sub(r"^(广州|深圳|珠海|汕头|佛山|江门|湛江|茂名|肇庆|惠州|梅州|汕尾|"
               r"河源|阳江|清远|东莞|中山|潮州|揭阳|云浮)(市)?", "", t)
    m = re.match(r"(.{2,45}?)(?:公开)?(?:招聘|招录|选聘|诚聘|招募|引进|面向)", t)
    return m.group(1).strip(" 　·-") if m else ""


def extract_headcount(title):
    """标题里的招录人数，如「…招聘3人公告」「…招募46人」。
    不限「招聘」和数字之间夹的字，避免「招聘合同制人员3人」漏抓。"""
    for m in re.finditer(r"(\d{1,4})\s*(?:名|人)(?!民)", title):
        n = int(m.group(1))
        if 0 < n < 2000:
            return n
    return 0


def extract_education(body):
    """学历要求：必须写成「硕士及以上 / 本科以上」这种明确门槛才算，
    避免正文里提一句「博士研究生年龄45岁以下」就被判成博士岗。"""
    ordered = [("博士", r"博士(?:研究生)?\s*(?:及以上|以上)"),
               ("硕士及以上", r"硕士(?:研究生)?\s*(?:及以上|以上)"),
               ("本科及以上", r"本科(?:学历)?\s*(?:及以上|以上)"),
               ("大专及以上", r"大专\s*(?:及以上|以上)|专科\s*(?:及以上|以上)")]
    for label, pat in ordered:
        if re.search(pat, body):
            return label
    return "详见原文"


def parse_detail(url, city, list_date):
    """抓详情页，返回公告 dict；失败返回 None"""
    html = fetch(url, timeout=20)
    if not html:
        return None

    s = soup_of(html)

    # 标题：h1 里去掉「进入阅读模式」
    h1 = s.find("h1")
    title = re.sub(r"进入阅读模式\s*$", "", h1.get_text(strip=True)) if h1 else ""

    # 正文：只取 div.lh_article，避开导航和课程广告
    art = s.select_one("div.lh_article")
    body = art.get_text("\n", strip=True) if art else ""

    if not title or len(body) < 80:
        return None

    # 抬头「来源：XX」+ 发布时间
    source_unit = ""
    tbox = s.select_one("div.zg_time")
    if tbox:
        a = tbox.find("a")
        if a:
            source_unit = a.get_text(strip=True)
        em = tbox.find("em")
        if em:
            list_date = (em.get_text(strip=True) or list_date)[:10]

    date = list_date or datetime.now().strftime("%Y-%m-%d")

    # 正文里可能藏着真实发布日期，优先用
    head = body[:400]
    real = find_date(head)
    if real and real != date:
        # 只认「20XX年X月X日」这种明确写法，避免误抓报名时间
        if re.search(r"发布(日期|时间)|更新(日期|时间)", head):
            date = real

    school = extract_school(title) or source_unit or "详见原文"
    # 「深圳大学」会被抠成「大学」这种没意义的词，退回用来源单位
    if len(school) < 4 or school in ("大学", "学院", "学校", "中学", "小学", "幼儿园"):
        school = source_unit or school
    level = "高校" if ("大学" in title or "学院" in title or "职业技术" in title) else "直属学校"
    if level == "高校":
        stage = "高校"
    else:
        stage = _stage_of(title)

    ann = {
        "title": title,
        "city": city,
        "school": school,
        "level": level,
        "stage": stage,
        "category": "其他",
        "establishment": _guess_est(title, body),
        "headcount": extract_headcount(title),
        "education": extract_education(body),
        "deadline": _extract_deadline(body, date) or _deadline_from_title(title),
        "recordedAt": date,
        "source": (source_unit + "（中公教育转载）") if source_unit else "中公教育转载",
        "sourceUrl": url,
        "content": {
            "intro": body[:300].replace("\n", " "),
            "targets": _extract_targets(body),
            "positions": _extract_positions(body),
            "conditions": _extract_conditions(body),
            "process": _extract_process(body),
            "signup": _extract_signup(body),
            "contact": _extract_contact(body),
        },
    }
    return ann


def load_existing():
    with open(OUT_FILE, encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r"window\.REAL_JOBS\s*=\s*(\[.*\]);", raw, re.S)
    if not m:
        raise SystemExit("data_anns.js 格式不认识，先跑一次 crawler.py")
    return raw, m, json.loads(m.group(1))


def title_key(title):
    """标题归一化，用来识别同一条公告被转载两次（如「英语老师」和「英语教师」）"""
    t = re.sub(r"\s+", "", title)
    t = t.replace("老师", "教师").replace("2026年", "2026")
    return t


def main():
    start = datetime.now()
    log("=" * 56)
    log("补充源：中公教育 广东教师招聘公告")
    log("=" * 56)

    raw, m, existing = load_existing()
    seen = {a.get("sourceUrl", "").rstrip("/") for a in existing}
    seen_titles = {title_key(a.get("title", "")) for a in existing}
    max_id = max([a.get("id", 0) for a in existing] or [0])
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")

    added, skipped_dup, skipped_old = [], 0, 0
    per_city = {}

    for slug, city in CITY_SLUGS:
        got = 0
        for page in range(1, MAX_PAGES + 1):
            url = LIST_TPL % slug if page == 1 else (LIST_TPL % slug) + "index_%d.html" % page
            html = fetch(url, timeout=20)
            if not html:
                break
            items = parse_list(html)
            if not items:
                break

            stop = False
            for date, title, link in items:
                if date < cutoff:
                    stop = True
                    continue
                if not want(title):
                    continue
                key = link.rstrip("/")
                if key in seen:
                    skipped_dup += 1
                    continue
                ann = parse_detail(link, city, date)
                if not ann:
                    continue
                if ann["deadline"] and ann["deadline"] < cutoff:
                    skipped_old += 1
                    continue
                tk = title_key(ann["title"])
                if tk in seen_titles:
                    skipped_dup += 1
                    continue
                seen_titles.add(tk)
                max_id += 1
                ann["id"] = max_id
                added.append(ann)
                seen.add(key)
                got += 1
                time.sleep(0.2)

            if stop:
                break
            time.sleep(0.3)

        per_city[city] = got
        log("  %-4s 新增 %d 条" % (city, got))

    if added:
        merged = existing + added
        new_json = json.dumps(merged, ensure_ascii=False, indent=2)
        out = raw[:m.start(1)] + new_json + raw[m.end(1):]
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(out)

    log("-" * 56)
    log("新增 %d 条，已存在跳过 %d 条，过期跳过 %d 条" % (len(added), skipped_dup, skipped_old))
    log("data_anns.js 现在共 %d 条公告" % (len(existing) + len(added)))
    log("耗时 %.1f 秒" % (datetime.now() - start).total_seconds())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("已手动中断")
        sys.exit(0)
