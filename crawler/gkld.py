# -*- coding: utf-8 -*-
"""补充源：公考雷达「广东 · 教师 · 招考公告」（www.gongkaoleida.com）

为什么加这个源：
  这是目前广东教师招聘公告最全的聚合站，一天几十条、七天几百条，
  而且幼儿园/中小学/中职/高职全都有，中公和事业单位网都覆盖不全。

怎么抓：
  这站有阿里云 WAF 拦截（直接 requests 只会拿到一段验证脚本），
  而且正文是前端渲染的，所以只能用真浏览器打开。这里用 Playwright 驱动
  本机自带的 Edge / Chrome（不用额外下载浏览器）。

用法：
    python crawler/gkld.py

输出：
    合并进 crawler/data_anns.js（按 sourceUrl + 标题去重）
    必须在 crawler.py 之后跑。
"""
import os
import re
import sys
import json
import time
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from crawler import (_extract_deadline, _deadline_from_title, _guess_est,
                     _stage_of, _extract_targets, _extract_positions,
                     _extract_conditions, _extract_process, _extract_signup,
                     _extract_contact)
from sydw import (extract_school, extract_headcount, extract_education,
                  city_of, DISTRICT_2_CITY)

OUT_FILE = os.path.join(BASE_DIR, "data_anns.js")

# 2129=广东  中间=城市id  59=教师  末尾 124=招考公告（0=全部资讯类型）
LIST_TPL = "https://www.gongkaoleida.com/area/2129-%d-0-59-124"
# 这站不登录只给第一页 30 条（?page=2 换了也没用，试过），
# 所以按城市分开抓，21 个市 × 30 条 = 最多 630 条，比只抓「全省」多得多
CITY_IDS = [
    ("广州", 2130), ("韶关", 2144), ("深圳", 2156), ("珠海", 2164),
    ("汕头", 2169), ("佛山", 2178), ("江门", 2185), ("湛江", 2194),
    ("茂名", 2205), ("肇庆", 2212), ("惠州", 2222), ("梅州", 2229),
    ("汕尾", 2239), ("河源", 2245), ("阳江", 2253), ("清远", 2259),
    ("东莞", 2269), ("中山", 2270), ("潮州", 2271), ("揭阳", 2276),
    ("云浮", 2283),
]
MAX_DETAIL = 80      # 每次最多打开 80 个详情页，剩下的下次跑再补
KEEP_DAYS = 45

KEEP_WORDS = ("招聘", "招录", "选聘", "诚聘", "招募", "引进", "招考")
SKIP_WORDS = ("拟录用", "拟聘用", "拟聘", "公示", "成绩", "体检", "准考证",
              "资格复审", "资格审核", "资格审查", "审核通知", "报名情况", "考察",
              "递补", "录用名单", "笔试", "面试", "入围", "拟进入", "放弃",
              "补充公告", "延期", "更正", "调整公告",
              "基层公共就业创业服务", "公益性岗位", "社区工作者", "辅警",
              "协管员", "网格员", "专职消防", "后备干部", "选调生", "三支一扶",
              "村官", "编外人员招聘")


def log(msg):
    print(msg, flush=True)


def launch(p):
    """用系统自带浏览器，省得下载 100 多 MB。返回 (browser, 说明)"""
    for ch in ("msedge", "chrome"):
        try:
            return p.chromium.launch(channel=ch, headless=True), ch
        except Exception:
            continue
    return p.chromium.launch(headless=True), "playwright自带chromium"


def want(title):
    if any(k in title for k in SKIP_WORDS):
        return False
    return any(k in title for k in KEEP_WORDS)


def city_by_label(labels, title):
    for lab in labels:
        lab = lab.strip("[]（）() ")
        if lab in DISTRICT_2_CITY:
            return DISTRICT_2_CITY[lab]
    return city_of(title)


def read_list(pg):
    """读当前页的 30 条，返回 [{region, labels, title, url}]"""
    return pg.evaluate("""() => [...document.querySelectorAll('div.notice-list li')].map(li => {
        const a = li.querySelector('a');
        return {
            labels: [...li.querySelectorAll('i.notice-label')].map(i => i.innerText.trim()),
            title: a ? (a.getAttribute('title') || a.innerText).trim() : '',
            url: a ? a.href : ''
        };
    })""")


def clean_body(raw):
    """把详情页正文前面那堆导航砍掉"""
    i = raw.find("来源：")
    txt = raw[i:] if i >= 0 else raw
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    # 去掉「来源：xxx」那一行和那句广告提示
    lines = [l for l in lines if not l.startswith("来源：")]
    lines = [l for l in lines if "公考雷达APP整理发布" not in l]
    return "\n".join(lines)


def parse_detail(pg, url, list_title, city):
    try:
        pg.goto(url, timeout=45000, wait_until="domcontentloaded")
    except Exception:
        return None
    pg.wait_for_timeout(1300)
    try:
        raw = pg.inner_text("body")
    except Exception:
        return None
    if not raw or len(raw) < 200:
        return None

    body = clean_body(raw)
    if len(body) < 100:
        return None

    title = list_title
    m = re.search(r"(20\d{2}-\d{2}-\d{2})\s+\d{2}:\d{2}", raw)
    date = m.group(1) if m else datetime.now().strftime("%Y-%m-%d")

    school = extract_school(title) or "详见原文"
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
        # 这站的「来源」要登录才显示，所以只能如实写「公考雷达转载」
        "source": "公考雷达（转载）",
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
    t = re.sub(r"[（(]?第[一二三四五六七八九十\d]+批[)）]?", "", t)
    return t.replace("老师", "教师").replace("2026年", "2026")


def main():
    from playwright.sync_api import sync_playwright

    start = datetime.now()
    log("=" * 56)
    log("补充源：公考雷达 · 广东教师招考公告")
    log("=" * 56)

    raw, m, existing = load_existing()
    seen = {a.get("sourceUrl", "").rstrip("/") for a in existing}
    seen_titles = {title_key(a.get("title", "")) for a in existing}
    max_id = max([a.get("id", 0) for a in existing] or [0])
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")

    added = []

    with sync_playwright() as p:
        browser, how = launch(p)
        log("浏览器：%s" % how)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000},
                                  locale="zh-CN")
        pg = ctx.new_page()

        # ---- 1. 按城市翻列表（这站不登录只给 30 条，只能靠分城市扩大覆盖）----
        rows = []
        for city, cid in [("", 0)] + CITY_IDS:
            url = LIST_TPL % cid
            try:
                pg.goto(url, timeout=60000, wait_until="domcontentloaded")
                pg.wait_for_timeout(3500)
                items = read_list(pg)
            except Exception:
                items = []
            if not items:
                # 124（招考公告）筛不出来时退回「全部资讯类型」
                try:
                    pg.goto(url[:-3] + "-0", timeout=60000, wait_until="domcontentloaded")
                    pg.wait_for_timeout(3500)
                    items = read_list(pg)
                except Exception:
                    items = []
            for it in items:
                it["city"] = city
            rows.extend(items)
            log("  %-6s %3d 条" % (city or "全省", len(items)))
        log("列表共读到 %d 条（含各种资讯类型）" % len(rows))

        # ---- 2. 过滤 ----
        todo = []
        batch = set()
        for it in rows:
            t = it["title"]
            if not t or "/article/" not in it["url"]:
                continue
            key = it["url"].rstrip("/")
            if key in seen or key in batch:
                continue
            if not want(t):
                continue
            if title_key(t) in seen_titles:
                continue
            batch.add(key)
            todo.append(it)
        log("去重 + 过滤后需抓详情 %d 条（本次上限 %d）" % (len(todo), MAX_DETAIL))

        # ---- 3. 抓详情 ----
        for i, it in enumerate(todo[:MAX_DETAIL], 1):
            city = it["city"] or city_by_label(it["labels"], it["title"])
            ann = parse_detail(pg, it["url"], it["title"], city)
            if not ann:
                continue
            if ann["deadline"] and ann["deadline"] < cutoff:
                continue
            tk = title_key(ann["title"])
            if tk in seen_titles:
                continue
            seen_titles.add(tk)
            seen.add(it["url"].rstrip("/"))
            max_id += 1
            ann["id"] = max_id
            added.append(ann)
            log("  [%d/%d] %s | %s | %s" % (i, min(len(todo), MAX_DETAIL),
                                            ann["city"], ann["deadline"] or "未标明",
                                            ann["title"][:38]))
        browser.close()

    if added:
        # 公考雷达是第三方，只当"发现渠道"：写进发现清单，绝不碰 data_anns.js。
        disc = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "discovered_gkld.json")
        try:
            old = json.load(open(disc, encoding="utf-8"))
        except Exception:
            old = []
        seen_urls = {x.get("sourceUrl") for x in old}
        for a in added:
            if a.get("sourceUrl") not in seen_urls:
                old.append(a)
        with open(disc, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=1)
        log("    发现 %d 条，已写入 discovered_gkld.json（不入库，等反推官方原文）" % len(added))

    log("-" * 56)
    log("发现 %d 条公告" % len(added))
    log("⛔ 第三方数据不入库，data_anns.js 未改动（共 %d 条官方公告）" % len(existing))
    log("耗时 %.1f 秒" % (datetime.now() - start).total_seconds())


if __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    try:
        main()
    except ImportError:
        log("[跳过] 没装 playwright，先执行：pip install playwright")
        sys.exit(0)
    except KeyboardInterrupt:
        log("已手动中断")
        sys.exit(0)
