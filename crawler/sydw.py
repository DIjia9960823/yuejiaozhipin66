# -*- coding: utf-8 -*-
"""补充源：全国事业单位招聘网「事业单位 · 招聘公告」（www.qgsydw.com）

为什么加这个源：
  很多区县教育局、公办学校、高职院校的编制内招聘，是把公告发到「全国事业单位
  招聘网」的（因为这站同时是它们在用的报名系统）。这些公告学校官网往往不发，
  我们原来的官方源抓不到。

  这个源是纯服务端渲染，不用浏览器就能抓；列表每页 30 条、带「地区」字段，
  我们只留「广东」的、且标题是教师/学校类招聘的。

用法：
    python crawler/sydw.py

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

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from crawler import (soup_of, _extract_deadline, _deadline_from_title, _guess_est,
                     _stage_of, _extract_targets, _extract_positions,
                     _extract_conditions, _extract_process, _extract_signup,
                     _extract_contact)

OUT_FILE = os.path.join(BASE_DIR, "data_anns.js")

LIST_BASE = "https://www.qgsydw.com/qgsydw/recruit/insrecruit/"
MAX_PAGES = 40     # 每页 30 条（全国），40 页≈1200 条，大约覆盖一个多月
KEEP_DAYS = 45     # 只收这么多天内的公告

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Referer": "https://www.qgsydw.com/qgsydw/index.html",
}

# 标题里出现这些词，才认为是「招聘」类公告
KEEP_WORDS = ("招聘", "招录", "选聘", "诚聘", "招募", "引进", "招考")
# 还得是跟「教师/学校」有关，否则会混进医院、国企、街道岗
TEACHER_WORDS = ("教师", "老师", "辅导员", "教研", "幼儿", "幼师", "园丁",
                 "学校", "学院", "大学", "中学", "小学", "职校", "技工",
                 "教育", "培训", "教职")
# 流程公告、非教师岗，直接丢掉
SKIP_WORDS = ("拟录用", "拟聘用", "拟聘", "公示", "成绩", "面试名单", "体检",
              "准考证", "资格复审", "报名情况", "考察", "递补", "录用名单",
              "笔试", "面试", "拟入围", "放弃",
              # 医疗 / 非教育事业单位
              "医院", "卫生院", "疾控", "妇幼", "保健院", "血站",
              # 其他非教师岗
              "基层公共就业创业服务", "公益性岗位", "社区工作者", "辅警",
              "协管员", "网格员", "专职消防", "后备干部", "选调生", "三支一扶",
              "村官", "编外人员招聘")

# 区县 → 地级市（标题里常写「番禺区」「南海区」而不写市名）
DISTRICT_CITY = {
    "广州": "越秀 荔湾 海珠 天河 白云 黄埔 番禺 花都 南沙 从化 增城",
    "韶关": "武江 浈江 曲江 始兴 仁化 翁源 乳源 新丰 乐昌 南雄",
    "深圳": "罗湖 福田 南山 宝安 龙岗 盐田 龙华 坪山 光明 大鹏",
    "珠海": "香洲 斗门 金湾 横琴 万山",
    "汕头": "龙湖 金平 濠江 潮阳 潮南 澄海 南澳",
    "佛山": "禅城 南海 顺德 三水 高明",
    "江门": "蓬江 江海 新会 台山 开平 鹤山 恩平",
    "湛江": "赤坎 霞山 坡头 麻章 遂溪 徐闻 廉江 雷州 吴川",
    "茂名": "茂南 电白 高州 化州 信宜",
    "肇庆": "端州 鼎湖 高要 广宁 怀集 封开 德庆 四会",
    "惠州": "惠城 惠阳 博罗 惠东 龙门 仲恺 大亚湾",
    "梅州": "梅江 梅县 大埔 丰顺 五华 平远 蕉岭 兴宁",
    "汕尾": "海丰 陆河 陆丰",
    "河源": "源城 紫金 龙川 连平 和平 东源",
    "阳江": "江城 阳西 阳东 阳春",
    "清远": "清城 清新 佛冈 阳山 连山 连南 英德 连州",
    "东莞": "虎门 长安 厚街 塘厦 松山湖 常平 寮步 大朗 凤岗 石龙 樟木头",
    "中山": "小榄 古镇 三乡 坦洲 火炬",
    "潮州": "湘桥 潮安 饶平",
    "揭阳": "榕城 揭东 揭西 惠来 普宁",
    "云浮": "云城 云安 新兴 郁南 罗定",
}
DISTRICT_2_CITY = {}
for _city, _ds in DISTRICT_CITY.items():
    for _d in _ds.split():
        DISTRICT_2_CITY[_d] = _city

CITY_NAMES = ["广州", "韶关", "深圳", "珠海", "汕头", "佛山", "江门", "湛江",
              "茂名", "肇庆", "惠州", "梅州", "汕尾", "河源", "阳江", "清远",
              "东莞", "中山", "潮州", "揭阳", "云浮"]


def log(msg):
    print(msg, flush=True)


def fetch(url, timeout=20, retry=1):
    """抓网页，按 GB18030 解码（这站是 gb2312），失败返回 None"""
    for _ in range(retry + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, verify=False,
                             allow_redirects=True)
            if r.status_code == 200:
                return r.content.decode("gb18030", "ignore")
        except Exception:
            pass
        time.sleep(1)
    return None


def parse_list(html):
    """列表页 → [(日期, 地区, 标题, 链接)]"""
    items = []
    for m in re.finditer(r'<span class="region1">([^<]*)</span>\s*'
                         r'<span class="title"[^>]*>\s*(.*?)\s*</span>.*?'
                         r'<span class="time">\s*(\d{4}-\d{2}-\d{2})', html, re.S):
        region, title, date = m.group(1).strip(), m.group(2).strip(), m.group(3)
        # 链接在这一条最前面，往前找
        head = html[max(0, m.start() - 900):m.start()]
        urls = re.findall(r'href="(/qgsydw/recruit/insrecruit/\d{8}/\d+\.html)"', head)
        if not urls:
            continue
        title = re.sub(r"<[^>]+>", "", title).strip()
        if title:
            items.append((date, region, title, "https://www.qgsydw.com" + urls[-1]))
    return items


def want(title):
    if not any(k in title for k in KEEP_WORDS):
        return False
    if not any(k in title for k in TEACHER_WORDS):
        return False
    if any(k in title for k in SKIP_WORDS):
        return False
    return True


def city_of(title):
    """先看标题里有没有市名，再看有没有区县名"""
    for c in CITY_NAMES:
        if c in title:
            return c
    for d, c in DISTRICT_2_CITY.items():
        if d in title:
            return c
    return "省直"


def extract_school(title):
    """从标题里抠学校/单位名，例：
    「广东艺术职业学院2026年公开招聘辅导员公告（第二批）」→ 广东艺术职业学院
    「2026年广州市海珠区教育系统高校毕业生招聘公告」→ 广州市海珠区教育系统
    """
    m = re.search(r"(?:公开)?(?:招聘|招录|选聘|诚聘|招募|招考|引进)", title)
    head = title[:m.start()] if m else ""
    head = re.sub(r"20\d{2}\s*年(度|下半年|上半年)?", "", head)
    head = re.sub(r"\d{1,2}\s*月", "", head)
    head = re.sub(r"^(关于|开展|做好|印发|发布|转发)", "", head)
    head = re.sub(r"(校园|面向|专场|公开)$", "", head)
    head = head.strip(" 　·-—、，,")
    if len(head) < 4 or head in ("大学", "学院", "学校", "中学", "小学", "幼儿园"):
        return ""
    return head


def extract_headcount(title, body=""):
    """标题里的人数；标题没写就看正文开头（「公开招聘3名专职辅导员」）"""
    for text in (title, body[:800]):
        for m in re.finditer(r"(\d{1,4})\s*(?:名|人)(?!民)", text):
            n = int(m.group(1))
            if 0 < n < 2000:
                return n
    return 0


def extract_education(body):
    ordered = [("博士", r"博士(?:研究生)?\s*(?:及以上|以上)"),
               ("硕士及以上", r"硕士(?:研究生)?\s*(?:及以上|以上)"),
               ("本科及以上", r"本科(?:学历)?\s*(?:及以上|以上)"),
               ("大专及以上", r"大专\s*(?:及以上|以上)|专科\s*(?:及以上|以上)")]
    for label, pat in ordered:
        if re.search(pat, body):
            return label
    return "详见原文"


def parse_detail(url, title0, list_date):
    html = fetch(url)
    if not html:
        return None
    s = soup_of(html)

    box = s.select_one("div.mainC-title")
    title = box.get_text(strip=True) if box else title0
    title = re.sub(r"-全国事业单位招聘网$", "", title)

    art = s.select_one("div.info-main")
    body = art.get_text("\n", strip=True) if art else ""
    if not title or len(body) < 80:
        return None

    date = list_date
    info = s.select_one("div.mainC-info")
    if info:
        m = re.search(r"发布(?:时间|日期)[：:]\s*(\d{4}-\d{2}-\d{2})", info.get_text(" ", strip=True))
        if m:
            date = m.group(1)

    # 站点自己标注的「文章来源」，多数写「全国事业单位招聘网」
    src_unit = "全国事业单位招聘网"

    city = city_of(title)
    school = extract_school(title) or "详见原文"
    # 「广州大学附属中学」标题里有「大学」但其实是中学，先看有没有中小学字样
    is_mid_or_low = bool(re.search(r"中学|小学|幼儿园|附中|附小|初中|高中", title))
    is_high = (not is_mid_or_low) and ("大学" in title or "学院" in title or "职业技术" in title)
    level = "高校" if is_high else "直属学校"
    stage = "高校" if is_high else _stage_of(title)

    return {
        "title": title,
        "city": city,
        "school": school,
        "level": level,
        "stage": stage,
        "category": "其他",
        "establishment": _guess_est(title, body),
        "headcount": extract_headcount(title, body),
        "education": extract_education(body),
        "deadline": _extract_deadline(body, date) or _deadline_from_title(title),
        "recordedAt": date,
        "source": src_unit,
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


def load_existing():
    with open(OUT_FILE, encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r"window\.REAL_JOBS\s*=\s*(\[.*\]);", raw, re.S)
    if not m:
        raise SystemExit("data_anns.js 格式不认识，先跑一次 crawler.py")
    return raw, m, json.loads(m.group(1))


def title_key(title):
    t = re.sub(r"\s+", "", title)
    return t.replace("老师", "教师").replace("2026年", "2026")


def main():
    start = datetime.now()
    log("=" * 56)
    log("补充源：全国事业单位招聘网 · 广东事业单位招聘公告")
    log("=" * 56)

    raw, m, existing = load_existing()
    seen = {a.get("sourceUrl", "").rstrip("/") for a in existing}
    seen_titles = {title_key(a.get("title", "")) for a in existing}
    max_id = max([a.get("id", 0) for a in existing] or [0])
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")

    added, dup, old, scanned_gd = [], 0, 0, 0

    for page in range(1, MAX_PAGES + 1):
        url = LIST_BASE + ("index.html" if page == 1 else "index_%d.html" % page)
        html = fetch(url)
        if not html:
            log("  第 %d 页抓不到，停止" % page)
            break
        items = parse_list(html)
        if not items:
            log("  第 %d 页没有条目，停止" % page)
            break

        oldest = min(i[0] for i in items)
        page_new = 0
        for date, region, title, link in items:
            if region != "广东":
                continue
            scanned_gd += 1
            if date < cutoff:
                continue
            if not want(title):
                continue
            key = link.rstrip("/")
            if key in seen:
                dup += 1
                continue
            ann = parse_detail(link, title, date)
            time.sleep(0.25)
            if not ann:
                continue
            if ann["deadline"] and ann["deadline"] < cutoff:
                old += 1
                continue
            tk = title_key(ann["title"])
            if tk in seen_titles:
                dup += 1
                continue
            seen_titles.add(tk)
            seen.add(key)
            max_id += 1
            ann["id"] = max_id
            added.append(ann)
            page_new += 1

        log("  第 %-2d 页  广东 %2d 条  新增 %d  最新 %s"
            % (page, sum(1 for i in items if i[1] == "广东"), page_new, items[0][0]))
        if oldest < cutoff:
            log("  已翻到 %s 之前的公告，停止" % cutoff)
            break
        time.sleep(0.3)

    if added:
        merged = existing + added
        new_json = json.dumps(merged, ensure_ascii=False, indent=2)
        out = raw[:m.start(1)] + new_json + raw[m.end(1):]
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(out)

    log("-" * 56)
    log("扫到广东公告 %d 条，新增 %d 条，已存在跳过 %d 条，过期跳过 %d 条"
        % (scanned_gd, len(added), dup, old))
    log("data_anns.js 现在共 %d 条公告" % (len(existing) + len(added)))
    log("耗时 %.1f 秒" % (datetime.now() - start).total_seconds())


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    try:
        main()
    except KeyboardInterrupt:
        log("已手动中断")
        sys.exit(0)
