# -*- coding: utf-8 -*-
"""反推模块：用公考雷达发现公告 → 必应搜索找官方原文 → 抓官方内容入库

为什么需要这个：
  公考雷达每天有几十条广东教师公告，但很多不在我们现有的官方源里（区/县教育局、
  民办学校等）。这个脚本用公考雷达当"发现渠道"，再把每条公告反推到官方原文
  （.gov.cn / .edu.cn），只收官方内容，不收第三方转载。

用法：
    python crawler/reverse.py

输出：
    合并进 crawler/data_anns.js（按 sourceUrl 去重）
"""
import os
import re
import sys
import json
import time
from datetime import datetime, timedelta
from urllib.parse import quote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from crawler import (_extract_deadline, _deadline_from_title, _guess_est,
                     _stage_of, _extract_targets, _extract_positions,
                     _extract_conditions, _extract_process, _extract_signup,
                     _extract_contact, soup_of)
from sydw import (extract_school, extract_headcount, extract_education,
                  city_of, DISTRICT_2_CITY)

OUT_FILE = os.path.join(BASE_DIR, "data_anns.js")

# 公考雷达：广东教师招考公告，按城市抓
GKLD_CITY_URL = "https://www.gongkaoleida.com/area/2129-%d-0-59-124"
CITY_IDS = [
    ("广州", 2130), ("深圳", 2156), ("珠海", 2164), ("佛山", 2178),
    ("东莞", 2269), ("中山", 2270), ("惠州", 2222), ("江门", 2185),
]
MAX_ITEMS = 40      # 每次最多处理 40 条公告
SEARCH_SLEEP = 3    # 每次搜索间隔 3 秒，避免限流

# 官方域名白名单
OFFICIAL_DOMAINS = (".gov.cn", ".edu.cn")

# 流程类公告跳过
SKIP_WORDS = ("拟录用", "拟聘用", "拟聘", "公示", "成绩", "体检", "准考证",
              "资格复审", "资格审核", "资格审查", "笔试", "面试", "入围",
              "递补", "考察", "放弃")
KEEP_WORDS = ("招聘", "招录", "选聘", "诚聘", "招募", "引进", "招考")


def log(msg):
    print(msg, flush=True)


def want(title):
    if any(k in title for k in SKIP_WORDS):
        return False
    return any(k in title for k in KEEP_WORDS)


def load_existing():
    with open(OUT_FILE, encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r"window\.REAL_JOBS\s*=\s*(\[.*\]);", raw, re.S)
    if not m:
        raise SystemExit("data_anns.js 格式不认识")
    return raw, m, json.loads(m.group(1))


def title_key(title):
    t = re.sub(r"\s+", "", title)
    t = re.sub(r"[（(]?第[一二三四五六七八九十\d]+批[)）]?", "", t)
    return t.replace("老师", "教师").replace("2026年", "2026")


def fetch_official_body(pg, url):
    """打开官方页面，提取正文"""
    try:
        pg.goto(url, timeout=30000, wait_until="domcontentloaded")
        pg.wait_for_timeout(2500)
    except Exception:
        return "", ""
    try:
        # 找标题
        title = pg.evaluate("""() => {
            const h = document.querySelector('h1, .article-title, .title, .news_title');
            return h ? h.innerText.trim() : document.title;
        }""")
        # 提取正文：去掉 script/style，找最长文本块
        body = pg.evaluate("""() => {
            document.querySelectorAll('script, style, nav, header, footer, .nav, .header, .footer').forEach(e => e.remove());
            const candidates = [...document.querySelectorAll('div, article, section, p')].map(e => {
                const t = e.innerText || '';
                return {len: t.length, text: t};
            }).filter(x => x.len > 100);
            candidates.sort((a, b) => b.len - a.len);
            return candidates[0] ? candidates[0].text : document.body.innerText;
        }""")
        return title, body
    except Exception:
        return "", ""


def search_official(pg, query):
    """在必应搜索，返回 [(title, url)]，只保留官方域名"""
    try:
        pg.goto("https://cn.bing.com/search?q=" + quote(query),
                timeout=30000, wait_until="domcontentloaded")
        pg.wait_for_timeout(2500)
    except Exception:
        return []
    try:
        items = pg.evaluate("""() => {
            const out = [];
            document.querySelectorAll('li.b_algo').forEach(li => {
                const a = li.querySelector('h2 a');
                if (a) out.push({title: a.innerText.trim(), href: a.getAttribute('href')});
            });
            return out;
        }""")
    except Exception:
        return []
    # 只保留官方域名，且标题与搜索词相关（至少有 4 个公共字符）
    official = []
    qcore = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", query)
    for it in items:
        if not any(d in it["href"] for d in OFFICIAL_DOMAINS):
            continue
        tcore = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", it["title"])
        common = len(set(qcore) & set(tcore))
        if common >= 4:
            official.append(it)
    return official


def parse_announcement(title, body, date, city):
    """从官方正文解析公告字段"""
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
        "source": school if school != "详见原文" else "政府部门",
        "sourceUrl": "",  # 调用时填入
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


def main():
    from playwright.sync_api import sync_playwright

    start = datetime.now()
    log("=" * 56)
    log("反推模块：公考雷达发现 → 必应搜索 → 官方原文入库")
    log("=" * 56)

    raw, m, existing = load_existing()
    seen = {a.get("sourceUrl", "").rstrip("/") for a in existing}
    seen_titles = {title_key(a.get("title", "")) for a in existing}
    max_id = max([a.get("id", 0) for a in existing] or [0])
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

    added = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, locale="zh-CN")
        pg = ctx.new_page()

        # 1. 从公考雷达拿公告列表
        all_items = []
        for city, cid in CITY_IDS:
            url = GKLD_CITY_URL % cid
            try:
                pg.goto(url, timeout=40000, wait_until="domcontentloaded")
                pg.wait_for_timeout(4000)
                items = pg.evaluate("""() => [...document.querySelectorAll('div.notice-list li')].map(li => {
                    const a = li.querySelector('a');
                    return {title: a ? (a.getAttribute('title') || a.innerText).trim() : '', href: a ? a.href : ''};
                }).filter(x => x.title)""")
            except Exception:
                items = []
            for it in items:
                it["city"] = city
            all_items.extend(items)
            log("  %-4s %3d 条" % (city, len(items)))
            time.sleep(1)

        # 去重 + 过滤
        todo = []
        for it in all_items:
            t = it["title"]
            if not t or not want(t):
                continue
            if title_key(t) in seen_titles:
                continue
            if any(d in it["href"] for d in ("gongkaoleida",)):
                # 公考雷达链接跳过，只用标题
                pass
            todo.append(it)
        # 去重标题
        seen_todo = set()
        unique_todo = []
        for it in todo:
            tk = title_key(it["title"])
            if tk not in seen_todo:
                seen_todo.add(tk)
                unique_todo.append(it)
        log("\n去重后待处理 %d 条，本次上限 %d 条" % (len(unique_todo), MAX_ITEMS))

        # 2. 逐条搜索官方原文
        for i, it in enumerate(unique_todo[:MAX_ITEMS], 1):
            title = it["title"]
            city = it["city"]
            log("\n[%d/%d] %s | %s" % (i, min(len(unique_todo), MAX_ITEMS), city, title[:40]))

            # 搜索
            results = search_official(pg, title)
            time.sleep(SEARCH_SLEEP)
            if not results:
                log("    未找到官方原文，跳过")
                continue

            # 取第一个官方结果
            official = results[0]
            log("    官方原文: %s" % official["href"][:80])

            # 抓官方正文
            official_title, body = fetch_official_body(pg, official["href"])
            if not body or len(body) < 100:
                log("    正文抓取失败，跳过")
                continue

            # 用官方页面的标题（如果和原标题匹配）
            final_title = title
            if official_title and len(official_title) > 6:
                # 取官方标题和原标题的较短者（去掉后缀" - 某某政府网"）
                final_title = re.sub(r"\s*[-_|].*$", "", official_title).strip() or title

            ann = parse_announcement(final_title, body, datetime.now().strftime("%Y-%m-%d"), city)
            ann["sourceUrl"] = official["href"]
            ann["source"] = "政府部门" if ".gov.cn" in official["href"] else ann.get("school", "学校")

            key = official["href"].rstrip("/")
            if key in seen:
                log("    已存在，跳过")
                continue
            tk = title_key(ann["title"])
            if tk in seen_titles:
                log("    标题已存在，跳过")
                continue

            seen.add(key)
            seen_titles.add(tk)
            max_id += 1
            ann["id"] = max_id
            added.append(ann)
            log("    ✅ 入库 | 截止:%s 人数:%s 学历:%s" % (
                ann["deadline"] or "未标明", ann["headcount"], ann["education"]))

        browser.close()

    if added:
        merged = existing + added
        out = raw[:m.start(1)] + json.dumps(merged, ensure_ascii=False, indent=2) + raw[m.end(1):]
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(out)

    log("\n" + "-" * 56)
    log("新增 %d 条官方公告" % len(added))
    log("data_anns.js 现在共 %d 条公告" % (len(existing) + len(added)))
    log("耗时 %.1f 分钟" % ((datetime.now() - start).total_seconds() / 60))


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
