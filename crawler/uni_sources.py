# -*- coding: utf-8 -*-
"""从广东各高校官网的招聘栏目抓官方招聘公告（只认学校自己域名）

入口：crawl_universities() 返回 jobs 列表，字段与 crawler.py 的公告一致。
数据来源：crawler/university_columns.json（由 probe_university_columns.py 探测生成）
"""
import json, os, re, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
COLUMNS = os.path.join(HERE, "university_columns.json")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
}
TIMEOUT = 15
WORKERS = 10
MAX_PER_SCHOOL = 5          # 每所学校最多收几条，防止刷屏
KEEP_DAYS = 180             # 只收近期公告（与网站整体保留天数一致）
_print_lock = threading.Lock()
_log = lambda m: None       # crawler.py 会替换成自己的日志函数


def set_logger(fn):
    global _log
    _log = fn


def _get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False, allow_redirects=True)
        r.encoding = r.apparent_encoding or r.encoding
        return r
    except Exception:
        return None


def _same_site(base, url):
    a = urlparse(base).netloc.replace("www.", "")
    b = urlparse(url).netloc.replace("www.", "")
    return not b or a == b or b.endswith("." + a) or a.endswith("." + b)


DATE_RE = re.compile(r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})")
URL_DATE_RE = re.compile(r"/(20\d{2})[/-](\d{2})(\d{2})/")
TITLE_KW = ("招聘", "招考", "引进", "诚聘", "聘用")
BAD_TITLE = ("结果", "名单", "公示", "成绩", "面试通知", "笔试通知", "体检", "拟聘", "录取",
             "招生", "招标", "采购", "中标", "废标",
             "考核", "评审", "资格审查", "资格复审", "面试", "笔试", "延迟", "变更",
             "补充公告", "流程", "协议书")


def _clean(t):
    return re.sub(r"\s+", "", t or "")


def _norm_url(u):
    """去掉重复的查询参数，同一个公告因为链接参数顺序不同会被当成两条"""
    p = urlparse(u)
    if not p.query:
        return u
    keep, seen = [], set()
    for kv in p.query.split("&"):
        k = kv.split("=")[0]
        if k in seen:
            continue
        seen.add(k)
        keep.append(kv)
    return p._replace(query="&".join(keep)).geturl()


def _list_links(col_url):
    """从栏目页取候选公告链接"""
    r = _get(col_url)
    if r is None or r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        text = _clean(a.get_text(" ", strip=True))
        if not (6 <= len(text) <= 60):
            continue
        if not any(k in text for k in TITLE_KW):
            continue
        if any(b in text for b in BAD_TITLE):
            continue
        url = urljoin(r.url, a["href"].strip())
        if not url.startswith("http") or not _same_site(col_url, url):
            continue
        key = _norm_url(url)
        if key in seen or url.rstrip("/") == col_url.rstrip("/"):
            continue
        seen.add(key)
        out.append((text, key))
    return out


def _deadline(body):
    """从正文里抓报名截止日期"""
    m = re.search(r"(?:截止|截至|报名时间)[^。；\n]{0,60}?(?:至|到|截止[至到]?)\s*"
                  r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", body)
    if not m:
        m = re.search(r"(?:截止时间|截止日期)[^。；\n]{0,20}?(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", body)
    if not m:
        return ""
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _detail(url, school, city, own, link_text):
    r = _get(url)
    if r is None or r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()

    h1 = soup.find("h1")
    title = _clean(h1.get_text()) if h1 else ""
    if not title or len(title) < 6:
        title = link_text or _clean(soup.title.get_text() if soup.title else "")
    title = title.replace("...", "").replace("…", "").replace("..", "")
    title = re.sub(r"^[\s\-—_|]+|[\s\-—_|]+$", "", title)[:80]
    if not any(k in title for k in TITLE_KW) or any(b in title for b in BAD_TITLE):
        return None

    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    body = re.sub(r"\s+", "", text)

    # 日期优先级：发布时间字段 > 页面顶部 > 链接里的 /年/月日/ > 全文第一个合法日期
    # （页面侧栏常挂着旧公告，直接取全文第一个日期会取错）
    day = None
    pm = re.search(r"(?:发布时间|发布日期|时间)[：:\s]{0,3}(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", text)
    if pm:
        try:
            day = datetime(int(pm.group(1)), int(pm.group(2)), int(pm.group(3)))
        except ValueError:
            day = None
    if day is None:
        for m in DATE_RE.finditer(text[:1500]):
            try:
                d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if 2015 <= d.year <= 2030:
                day = d
                break
    if day is None:
        m = URL_DATE_RE.search(r.url) or URL_DATE_RE.search(url)
        if m:
            try:
                day = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                day = None
    if day is None:
        for m in DATE_RE.finditer(text):
            try:
                d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if 2015 <= d.year <= 2030:
                day = d
                break
    if day is None:
        return None
    if day < datetime.now() - timedelta(days=KEEP_DAYS) or day > datetime.now() + timedelta(days=30):
        return None

    dl = _deadline(body)
    if dl and dl < datetime.now().strftime("%Y-%m-%d"):
        return None

    head = 0
    hm = re.search(r"招聘\s*(\d{1,4})\s*(?:名|人)", body) or re.search(r"(\d{1,4})\s*名(?:教师|专任教师|工作人员)", body)
    if hm:
        head = int(hm.group(1))

    est = "正式编" if ("事业编" in body or "编制内" in body or "纳入编制" in body) else "详见原文"

    intro = re.sub(r"\s+", " ", text)[:220]

    return {
        "title": title,
        "city": city,
        "school": school,
        "level": "高校",
        "stage": "高校",
        "category": "高校招聘",
        "establishment": est,
        "headcount": head,
        "education": "详见原文",
        "deadline": dl,
        "recordedAt": day.strftime("%Y-%m-%d"),
        "source": "%s官网" % school,
        "sourceUrl": r.url,
        "ownership": own,
        "content": {
            "intro": intro,
            "targets": [],
            "positions": "详见原文",
            "conditions": [],
            "process": "",
            "signup": "",
            "contact": "",
        },
    }


def _work(school, info):
    """一所学校：翻它的招聘栏目，取最近几条"""
    jobs, seen = [], set()
    for col in info.get("columns", [])[:2]:
        for text, url in _list_links(col["url"])[:12]:
            if url in seen:
                continue
            seen.add(url)
            j = _detail(url, school, info.get("city", ""), info.get("own", ""), text)
            if j:
                jobs.append(j)
            if len(jobs) >= MAX_PER_SCHOOL:
                return jobs
    return jobs


def crawl_universities():
    if not os.path.exists(COLUMNS):
        _log("    高校官网源未配置，跳过")
        return []
    cols = json.load(open(COLUMNS, encoding="utf-8"))
    targets = [(s, d) for s, d in cols.items() if d.get("columns")]
    _log("    高校官网源：%d 所学校有招聘栏目，开始抓取…" % len(targets))

    jobs, done = [], 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_work, s, d): s for s, d in targets}
        for f in as_completed(futs):
            done += 1
            try:
                jobs.extend(f.result())
            except Exception:
                pass
    _log("    高校官网源抓完：%d 所，得到 %d 条" % (len(targets), len(jobs)))
    return jobs
