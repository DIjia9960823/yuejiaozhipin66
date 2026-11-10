# -*- coding: utf-8 -*-
"""
粤师聘 · 教师招聘公告抓取脚本

用法（Windows）：双击「一键运行.bat」
用法（命令行）：python crawler.py

它会：
1. 逐个打开 sites.py 里配置的教育局官网
2. 自动找到「通知公告 / 公示公告」栏目
3. 抓取其中的文章，挑出「教师招聘」相关的公告
4. 抓取公告详情（标题、发布日期、招聘人数、学历、编制、截止时间等）
5. 生成 ../data.js，网站下次刷新就会显示真实数据

抓取结果会同时写入 crawler_log.txt，方便查看哪个网站失败。
"""

import html as html_lib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

from sources import (
    SOURCES,
    MAX_COLUMNS,
    MAX_ARTICLES_PER_SOURCE,
    MAX_PAGES_PER_COLUMN,
    KEYWORD_MUST,
    KEYWORD_TEACHER,
    KEYWORD_EXCLUDE,
    RECENT_DAYS,
    PRIVATE_RECENT_DAYS,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 输出到 crawler/ 自己目录下，避免覆盖根目录的职位 data.js
OUT_FILE = os.path.join(BASE_DIR, "data_anns.js")
LOG_FILE = os.path.join(BASE_DIR, "crawler_log.txt")
STATUS_FILE = os.path.join(BASE_DIR, "source_status.json")
SCHOOL_DB_FILE = os.path.join(BASE_DIR, "schools_db.json")   # 省教育厅学校名单（公办/民办）

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

COLUMN_WORDS = ["通知公告", "公示公告", "公告公示", "人事", "招聘", "招考", "政务公开", "人才", "师资"]

_log_lines = []
_log_lock = threading.Lock()
# 同时抓取的数据源数量（多线程提速；同一个源内部仍是顺序访问，避免被网站拉黑）
WORKERS = 6
# 连续失败这么多次的源，抓取时自动跳过（用 manage.py check 体检可复查）
SKIP_FAIL_STREAK = 3

# ===== 万行教师网 · 列表页抓取（公办公告 + 民办职位，全自动） =====
JOB910_WORKERS = 8          # 详情页并发线程数
JOB910_PUBLIC_PAGES = 20    # 公办公告翻页数（每页 10 条、按发布时间倒序，约覆盖最近 6 个月）
JOB910_PRIVATE_PAGES = 40   # 民办职位翻页数（每页 10 条，卡片自带学校名/城市/薪资）
JOB910_PUBLIC_LIST = "https://www.job910.com/jobs/search.html?areaCode=440000&pageIndex=%d"
JOB910_PRIVATE_LIST = "https://www.job910.com/job/search?companyType=10&areaCode=440000&pageIndex=%d"
# 广东 21 个地级市，用于判断职位是否在广东
JOB910_GD_CITIES = "广州|深圳|珠海|汕头|佛山|韶关|湛江|肇庆|江门|茂名|惠州|梅州|汕尾|河源|阳江|清远|东莞|中山|潮州|揭阳|云浮"
JOB910_CITY_LIST = JOB910_GD_CITIES.split("|")
# 教师岗位关键词（职位标题含这些词才算教师岗）
JOB910_TEACHER_KW = ["教师", "老师", "教学", "讲师", "教授", "班主任", "学科", "教研", "辅导员", "实验员", "教务", "德育", "园长"]


def log(msg):
    line = str(msg)
    with _log_lock:
        print(line)
        _log_lines.append(line)


_tls = threading.local()


def _set_err(msg):
    """记录失败原因（多线程下各记各的，互不覆盖）"""
    _tls.err = msg


def _last_err():
    return getattr(_tls, "err", "")


LAST_ERROR = ""  # 兼容旧脚本引用，并行抓取时请以 _last_err() 为准


def error_note(e):
    """把网络错误翻译成人话"""
    n = type(e).__name__
    msg = str(e)
    if "Timeout" in n:
        return "连接超时"
    if "SSL" in n:
        return "证书/加密错误"
    if "NameResolution" in n or "Name or service not known" in msg or "getaddrinfo" in msg:
        return "域名解析失败（网址可能已失效）"
    if "Connection" in n:
        return "无法连接"
    return "网络错误（%s）" % n


def fetch(url, timeout=25):
    """抓网页，返回文本；失败返回 None（原因可用 _last_err() 读取）"""
    global LAST_ERROR
    LAST_ERROR = ""
    _set_err("")
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=False, allow_redirects=True)
        if r.status_code != 200:
            msg = "网站拒绝访问（HTTP %d）" % r.status_code
            LAST_ERROR = msg
            _set_err(msg)
            return None
        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
            r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        msg = error_note(e)
        LAST_ERROR = msg
        _set_err(msg)
        return None


def soup_of(text):
    return BeautifulSoup(text, "html.parser")


def same_host(url, base):
    return url.startswith(("http://", "https://")) and base.split("/")[2] in url


def discover_columns(home_html, home_url):
    """从首页找「通知公告 / 公示公告」等栏目地址"""
    s = soup_of(home_html)
    found, priority = [], []
    for a in s.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if not text or len(text) > 20:
            continue
        if not any(w in text for w in COLUMN_WORDS):
            continue
        href = requests.compat.urljoin(home_url, a["href"])
        if not same_host(href, home_url):
            continue
        if any(x in href.lower() for x in (".jpg", ".png", ".zip", ".pdf", ".doc")):
            continue
        if href in found:
            continue
        found.append(href)
        # 招聘 / 招考 / 人事 栏目优先
        priority.append(2 if "招聘" in text else 1 if ("招考" in text or "人事" in text) else 0)
    ranked = [u for _, u in sorted(zip(priority, found), key=lambda x: -x[0])]
    return ranked[:MAX_COLUMNS]


ARTICLE_EXT = (".html", ".htm", ".shtml", ".psp", ".jsp", ".php")

ARTICLE_PAT = re.compile(
    r"(post_\d+|/content/|/t20\d{5,}|/art/|/detail/|/info/\d+/\d+|/a/\d+|/"
    r"[a-z]{2,6}\d{4,}_?\d*\.(?:html|htm|shtml|psp|jsp|php)|/\d{6,}\.?(?:html|htm|shtml|psp|jsp|php))",
    re.I,
)


def article_links(html, page_url):
    """从栏目页取出文章链接（标题, 地址）"""
    s = soup_of(html)
    items = []
    for a in s.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        href = requests.compat.urljoin(page_url, a["href"])
        if len(title) < 8:
            continue
        if not same_host(href, page_url):
            continue
        if not ARTICLE_PAT.search(href) and not href.lower().endswith(ARTICLE_EXT):
            continue
        if not re.search(r"\.(html|htm|shtml|psp|jsp|php)(\?|$)", href, re.I):
            continue
        items.append((title, href))
    # 去重
    seen, out = set(), []
    for t, h in items:
        if h in seen:
            continue
        seen.add(h)
        out.append((t, h))
    return out


def looks_like_recruit(title):
    if any(w in title for w in KEYWORD_EXCLUDE):
        return False
    if not any(w in title for w in KEYWORD_MUST):
        return False
    return any(w in title for w in KEYWORD_TEACHER)


def json_column_links(jurl):
    """部分网站（如深圳）栏目是JS动态加载，数据在JSON接口里，直接取文章列表"""
    h = fetch(jurl)
    if not h:
        return []
    try:
        data = json.loads(h)
    except Exception:
        return []
    out = []
    for a in data.get("articles", [])[:40]:
        t = (a.get("title") or "").strip()
        u = a.get("url") or ""
        if t and u:
            out.append((t, u))
    return out


def gkmlpt_links(base, cat, maxn=60):
    """广东省政府信息公开平台（gkmlpt）：栏目数据在 JSON 接口里，日期是秒级时间戳
    返回 (链接列表, 接口是否调通)。接口通但文章全过期时链接为空，用于区分 empty 和 fail。"""
    url = "%s/api/all/%s?page=1&size=20" % (base.rstrip("/"), cat)
    h = fetch(url)
    if not h:
        return [], False
    try:
        data = json.loads(h)
    except Exception:
        return [], False
    if not isinstance(data, dict) or "articles" not in data:
        return [], False
    cutoff = (datetime.now() - timedelta(days=RECENT_DAYS + 30)).timestamp()
    out = []
    for a in (data.get("articles") or [])[:200]:
        t = (a.get("title") or "").strip()
        u = a.get("url") or ""
        ts = a.get("date") or a.get("create_time") or 0
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            ts = 0
        if ts > 1e12:      # 毫秒时间戳
            ts /= 1000.0
        if ts and ts < cutoff:
            continue
        if t and u:
            out.append((t, u))
        if len(out) >= maxn:
            break
    return out, True


DATE_PATTERNS = [
    re.compile(r"发布(?:时间|日期)[:：]?\s*(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})"),
    re.compile(r"(?:时间|日期)[:：]?\s*(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})"),
    re.compile(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})"),
]


def find_date(text):
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 2000 < y < 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                return "%04d-%02d-%02d" % (y, mo, d)
    return ""


def body_text(s):
    """提取正文纯文本"""
    picked = None
    for tag in s.find_all(True):
        cid = (tag.get("id") or "") + " " + " ".join(tag.get("class") or [])
        cid = cid.lower()
        if any(k in cid for k in ("content", "article", "zoom", "text", "detail", "trs_editor")):
            t = tag.get_text("\n", strip=True)
            if len(t) > 200:
                picked = t
                break
    if not picked:
        ps = [p.get_text(" ", strip=True) for p in s.find_all("p")]
        picked = "\n".join(x for x in ps if x)
    return re.sub(r"\n{2,}", "\n", picked or "")


def title_of(s, fallback):
    # 很多政府站把真实文章标题放在 <meta name="ArticleTitle"> 里（h1 可能是站名）
    m = s.find("meta", attrs={"name": re.compile(r"^articletitle$", re.I)})
    if m and m.get("content"):
        return m["content"].strip()
    h1 = s.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    og = s.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    if s.title:
        t = s.title.get_text(strip=True)
        return re.split(r"[-_|]", t)[0].strip() or t
    return fallback


def to_md(s):
    return s or ""


# ===== 公告正文分章节提取（把「详见原文」换成真实内容） =====
SECTION_HEAD_RE = re.compile(
    r"^(?:[一二三四五六七八九十]+[、.]|[（(][一二三四五六七八九十]+[)）]"
    r"|\d+[、.．]|[（(]\d+[)）]|【|第[一二三四五六七八九十]+)")


def _is_heading(line):
    """判断某一行是不是小标题"""
    ln = line.strip()
    if not ln or len(ln) > 45:
        return False
    if SECTION_HEAD_RE.match(ln):
        return True
    return ln.endswith(("：", ":")) and len(ln) <= 26


def _section(body, keys, max_lines=8, min_len=20, must=None):
    """按小标题关键词截取一段正文：找到含关键词的标题行，取它下面的几行"""
    lines = [x.strip() for x in body.split("\n") if x.strip()]
    for i, ln in enumerate(lines):
        if any(k in ln for k in keys) and (len(ln) <= 20 or ln.endswith(("：", ":"))):
            buf = []
            for nxt in lines[i + 1:i + 1 + max_lines]:
                if _is_heading(nxt):   # 遇到下一个小标题就停，避免把标题混进正文
                    break
                buf.append(nxt)
                if sum(len(x) for x in buf) > 420:
                    break
            txt = " ".join(buf).strip()
            if len(txt) >= min_len and (must is None or any(w in txt for w in must)):
                return txt
    return ""


def _sentences_with(body, keys, maxn=3, maxlen=160):
    """从正文里挑出含关键词的短句"""
    out = []
    for seg in re.split(r"[。；\n]", body):
        seg = re.sub(r"\s+", "", seg)
        if 6 <= len(seg) <= maxlen and any(k in seg for k in keys) and not _is_heading(seg):
            if seg not in out:
                out.append(seg)
        if len(out) >= maxn:
            break
    return out


def _extract_targets(body):
    """招聘对象"""
    sec = _section(body, ["招聘对象", "招聘范围", "招聘对象及条件", "招聘对象和条件"],
                   must=["应届", "毕业生", "社会", "在职", "面向", "人员"])
    if sec:
        return [sec[:200]]
    got = _sentences_with(body, ["应届毕业生", "社会人员", "在职教师", "面向", "不限户籍"], maxn=2)
    return got


def _extract_positions(body):
    """招聘岗位 / 学科"""
    sec = _section(body, ["招聘岗位", "岗位表", "招聘计划", "招聘学科", "岗位设置",
                          "招聘职位", "岗位需求", "学科需求", "需求岗位"],
                   must=["教师", "学科", "岗位", "专业", "语文", "数学", "英语"])
    if sec:
        return sec[:220]
    # 没有明确的岗位章节就不猜，避免把正文里出现的学科词当成招聘岗位
    return "详见原文"


def _extract_conditions(body):
    """报考条件：先找条件章节，再补关键硬条件"""
    items = []
    sec = _section(body, ["基本条件", "报考条件", "应聘条件", "招聘条件", "资格条件",
                          "报名条件", "条件要求", "招聘要求"],
                   must=["学历", "年龄", "资格", "专业", "周岁", "本科", "硕士", "国民教育"])
    if sec:
        for part in re.split(r"[；;]|(?<=。)", sec):
            part = re.sub(r"\s+", " ", part).strip().rstrip("。、，,；; ")
            # 去掉前面的序号（1. / （2） 等），保留条件本体
            part = re.sub(r"^(?:[（(]\d+[)）]|\d+[、.．])\s*", "", part).rstrip("。、，,；; ")
            if (8 <= len(part) <= 120 and "招聘对象" not in part
                    and "公告如下" not in part
                    and any(k in part for k in ("周岁", "学历", "资格", "专业", "本科",
                                               "硕士", "博士", "经验", "能力", "素质",
                                               "品行", "身体", "国籍", "遵纪守法", "年龄"))
                    and not (len(part) <= 12 and part.endswith(
                        ("条件", "要求", "程序", "对象", "范围", "说明")))):
                items.append(part)
    if not items:
        items.extend(_sentences_with(
            body, ["教师资格证", "周岁", "本科及以上", "硕士研究生", "博士研究生", "学历要求"], maxn=4))
    # 单独补年龄、学历、资格证（章节里没提到时兜底）
    for pat, label in ((r"年龄(?:一般)?(?:在)?\s*(\d{2})\s*周岁以下", "年龄 %s 周岁以下"),
                       (r"(\d{2})\s*周岁以下", "年龄 %s 周岁以下")):
        m = re.search(pat, body)
        if m:
            line = label % m.group(1)
            if not any("周岁" in x for x in items):
                items.append(line)
            break
    out = []
    for x in items:
        if x and x not in out:
            out.append(x)
    return out[:5]


def _extract_process(body):
    """招聘程序"""
    sec = _section(body, ["招聘程序", "招聘流程", "选聘程序", "招聘办法", "考试程序",
                          "招聘步骤", "录用程序", "选聘流程", "招聘环节"],
                   must=["笔试", "面试", "体检", "考察", "公示", "聘用", "考试", "资格审核"])
    if sec:
        return sec[:220]
    steps = ["发布公告", "报名", "资格审查", "笔试", "面试", "体检", "考察", "公示", "聘用"]
    hit = [s for s in steps if s in body]
    return " → ".join(hit) if len(hit) >= 3 else ""


def _extract_signup(body):
    """报名方式 / 报名时间"""
    sec = _section(body, ["报名方式", "报名办法", "报名时间", "报名程序", "报名须知",
                          "应聘方式", "投递方式", "报名要求", "报名渠道", "报名方法"],
                   must=["报名", "投递", "发送", "http", "网址", "现场", "邮箱", "时间"])
    if sec:
        return sec[:220]
    got = _sentences_with(body, ["报名", "投递", "发送至", "邮箱"], maxn=3, maxlen=180)
    return "；".join(got)[:220]


def _extract_contact(body):
    """联系方式：联系人 / 电话 / 邮箱 / 地址"""
    parts = []
    m = re.search(r"联系人[：:]?\s*([\u4e00-\u9fa5·]{2,6}(?:\s*[、，,]\s*[\u4e00-\u9fa5·]{2,6})?)", body)
    if m:
        parts.append("联系人 " + re.sub(r"\s+", "", m.group(1)))
    tels = re.findall(r"(?:联系电话|咨询电话|联系电话及|电话)[：:]?\s*([0-9\-－—()（）\s]{7,22})", body)
    if not tels:
        tels = re.findall(r"(0\d{2,3}[-－]\d{7,8}|1[3-9]\d{9})", body)
    if tels:
        uniq = list(dict.fromkeys(t.strip(" -－—()（）") for t in tels if t.strip(" -－—()（）")))
        if uniq:
            parts.append("电话 " + "、".join(uniq[:3]))
    m = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", body)
    if m:
        parts.append("邮箱 " + m.group(0))
    m = re.search(r"(?:报名|投递|邮寄|通讯|联系)地址[：:]\s*([^。\n]{4,45})", body)
    if m:
        parts.append("地址 " + re.sub(r"\s+", "", m.group(1)))
    return "；".join(parts)


def _guess_est(title, body):
    """判断编制性质：正式编 / 合同制 / 详见原文

    坑：正文里写「非事业编制」时，简单判「含事业编制」会误判成正式编，
    所以先把否定说法摘掉再找正式编关键词。
    """
    txt = title + " " + body
    neg = re.sub(r"非事业编制|非事业单位编制|非编制|非在编|编外|不含编制|不纳入编制", "", txt)
    formal = ("纳入事业编制", "事业单位编制", "事业编制", "事业编", "编制内",
              "正式在编", "实名编制", "有编制", "纳入编制管理", "在编人员")
    contract = ("非事业编制", "非在编", "编外", "劳务派遣", "合同制", "临聘",
                "非编制", "聘用制", "劳动合同", "政府购买服务")
    has_formal = any(k in neg for k in formal)
    has_contract = any(k in txt for k in contract)
    if has_formal:
        return "正式编"
    if has_contract:
        return "合同制"
    return "详见原文"


DATE_FULL_RE = re.compile(r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*[日号]?")
DATE_MD_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")


def _date_tokens(seg, ref_year):
    """取出句子里所有日期，返回 (起, 止, 年, 月, 日, 是否写了年份)"""
    out = []
    for m in DATE_FULL_RE.finditer(seg):
        out.append((m.start(), m.end(), int(m.group(1)),
                    int(m.group(2)), int(m.group(3)), True))
    for m in DATE_MD_RE.finditer(seg):
        out.append((m.start(), m.end(), ref_year,
                    int(m.group(1)), int(m.group(2)), False))
    out.sort()
    dedup = []
    for t in out:      # 年月日 会同时命中两个正则，去重
        if dedup and t[0] < dedup[-1][1]:
            continue
        if 1 <= t[3] <= 12 and 1 <= t[4] <= 31:
            dedup.append(t)
    return dedup


def _extract_deadline(body, ref_date):
    """从正文里找报名截止日期，找不到就留空（宁缺勿错）

    很多公告写成「（一）网络报名\n1.时间：2026年11月3日至11月10日」，
    日期并不和「报名」在同一句里，所以改成：以「报名/投递」为锚点，
    往后取一小段文字找日期，而不是按句子切。
    """
    try:
        ref = datetime.strptime(ref_date, "%Y-%m-%d")
    except Exception:
        ref = datetime.now()
    txt = body.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    txt = re.sub(r"[ \t\u3000]+", "", txt)

    def to_dt(tok):
        y, mo, d, no_year = tok[2], tok[3], tok[4], not tok[5]
        try:
            dt = datetime(y, mo, d)
        except ValueError:
            return None
        if dt < ref:
            # 没写年份又早于发布日期：只有跨年（12 月发公告、1-3 月截止）才顺延
            if not no_year or mo > 3:
                return None
            try:
                dt = datetime(y + 1, mo, d)
            except ValueError:
                return None
            if (dt - ref).days > 120:
                return None
        if (dt - ref).days > 200:
            return None
        return dt

    def pick(win):
        toks = _date_tokens(win, ref.year)
        if not toks:
            return None
        # 起止区间取后一个；多个考点/批次（多个区间）取最晚的那个
        if len(toks) >= 2 and re.search(r"[至到—－~～\-]", win[toks[0][1]:toks[1][0]]):
            if len(toks) >= 3:
                return max(toks[1:], key=lambda t: (t[2], t[3], t[4]))
            return toks[1]
        if len(toks) == 1:
            return toks[0]
        return None

    cands = []
    for m in re.finditer(r"报名|投递|申请|简历|提交|应聘", txt):
        win = txt[m.start(): m.start() + 180]
        # 后面的笔试/面试日期不是报名截止，切掉
        win = re.split(r"笔试|面试|考试时间|资格审查结果|体检|公示", win)[0]
        tok = pick(win)
        if tok is None:
            # 有时日期写在关键词前面：「请于11月10日前提交简历」
            back = txt[max(0, m.start() - 60): m.start() + 40]
            tok = pick(back)
        if tok is None:
            continue
        dt = to_dt(tok)
        if not dt:
            continue
        head = win[:40]
        score = 0
        # 「报名时间：」「报名截止日期：」这种才是真正的截止时间
        if any(k in head for k in ("报名时间", "报名日期", "报名截止时间",
                                   "报名截止日期", "报名起止", "报名期限")):
            score += 3
        if any(k in head for k in ("截止", "截至", "结束")):
            score += 2
        if "时间" in head or "日期" in head:
            score += 1
        # 日期离「报名」太远，多半是条件说明里的日期（如「报名截止之日前取得…」）
        if tok[0] > 80:
            score -= 2
        cands.append((score, -m.start(), dt))
    if not cands:
        return ""
    cands.sort(reverse=True)
    return cands[0][2].strftime("%Y-%m-%d")


def _deadline_from_title(title):
    """标题里写明的截止日期，只认两种已验证写法（宁缺勿错）：
    「…公告-2026/10/30截止…」（日期在「截止」前）
    「…（截止至2025.9.15）」（「截止至/到」后跟日期）
    注意：有的列表页会在标题尾巴拼上发布日期（如 …截止2026-10-12），
    所以「截止」后直接跟日期、中间没有「至/到」的一概不认。"""
    txt = title.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    m = (re.search(r"(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*[日号]?\s*截止", txt)
         or re.search(r"截止[至到]\s*(20\d{2})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})\s*[日号]?", txt))
    if not m:
        return ""
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def parse_detail(url, city, source_name, hint_title=""):
    html = fetch(url)
    if not html:
        return None
    s = soup_of(html)
    # 优先用详情页自己的标题（列表页的标题可能被截断，如 &quo... 结尾）；
    # 但以「网站/首页」结尾的是站名不是文章标题，不能用
    page_title = title_of(s, "")
    hint = (hint_title or "").strip()
    clean_name = re.sub(r"（.*?）|\(.*?\)", "", source_name).strip()
    # 有些民办学校详情页的标题只写学校名（不是文章标题），这时改用列表里的标题
    page_has_kw = any(w in page_title for w in KEYWORD_MUST)
    hint_has_kw = any(w in hint for w in KEYWORD_MUST)
    if (page_title and len(page_title) >= 8
            and not re.search(r"(网站|首页)$", page_title)
            and page_title not in (source_name, clean_name)
            and (page_has_kw or not hint_has_kw)):
        title = page_title
    else:
        title = hint or page_title
    title = html_lib.unescape(title).strip()
    body = body_text(s)
    if not title:
        return None
    # 标题里写死早年月份的老公告（如「2020年公开招聘…」），别被当成今天发布的
    ym = re.search(r"(20\d{2})年", title)
    if ym and int(ym.group(1)) < datetime.now().year - 1:
        return None

    date = find_date(body[:4000]) or find_date(s.get_text(" ", strip=True)[:4000]) \
        or datetime.now().strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    if date > today:      # 正文里出现的未来日期（比如招生时间）不算发布日期
        date = today

    head = 0
    for pat in (r"招聘[\u4e00-\u9fa5、（）()\s]{0,20}?(\d{1,4})\s*(?:名|人)",
                r"(?:招聘|招录|选聘)[^。]{0,15}?(\d{1,4})\s*(?:名|人)",
                r"共计?\s*(\d{1,4})\s*(?:名|人)"):
        m = re.search(pat, body[:3000])
        if m:
            head = int(m.group(1))
            break

    edu = "详见原文"
    m = re.search(r"(?:学历|学位)(?:要求)?[^。]{0,20}?(博士|硕士|本科|大专)", body)
    if not m:
        m = re.search(r"(博士研究生|硕士研究生|本科(?:研究生)?)(?:及以上|以上)", body)
    if m:
        v = m.group(1)
        edu = {"博士": "博士", "博士研究生": "博士", "硕士": "硕士及以上",
               "硕士研究生": "硕士及以上", "本科": "本科及以上",
               "本科研究生": "本科及以上", "大专": "大专及以上"}.get(v, "详见原文")

    est = _guess_est(title, body)

    stage = "中小学"
    for k, v in (("幼儿园", "幼儿园"), ("小学", "小学"), ("初中", "中学"), ("高中", "中学"),
                 ("高校", "高校"), ("大学", "高校"), ("学院", "高校"), ("职业", "高职"),
                 ("高职", "高职"), ("中职", "高职")):
        if k in title:
            stage = v
            break
    else:
        for k, v in (("幼儿园", "幼儿园"), ("小学", "小学"), ("初中", "中学"), ("高中", "中学"),
                     ("高校", "高校"), ("职业", "高职"), ("中职", "高职")):
            if k in body:
                stage = v
                break

    deadline = _extract_deadline(body, date) or _deadline_from_title(title)

    intro = " ".join(body.split())[:160]
    # 分章节抽取正文细节，替换原来的「详见原文」
    targets = _extract_targets(body)
    positions = _extract_positions(body)
    conditions = _extract_conditions(body)
    process = _extract_process(body)
    signup = _extract_signup(body)
    contact = _extract_contact(body)
    return {
        "title": title,
        "city": city,
        "school": source_name,
        "level": "直属学校",
        "stage": stage,
        "category": "公办编制" if est == "正式编" else "其他",
        "establishment": est,
        "headcount": head,
        "education": edu,
        "deadline": deadline,
        "recordedAt": date,
        "source": source_name + "官网",
        "sourceUrl": url,
        "content": {
            "intro": intro or "详见官方公告原文。",
            "targets": targets or ["详见原文"],
            "positions": positions or "详见原文",
            "conditions": conditions or ["详见官方公告原文"],
            "process": process or "详见官方公告原文",
            "signup": signup or "详见官方公告原文",
            "contact": contact or "详见官方公告原文（具体信息以官方发布为准）",
        },
    }


def crawl_source(src):
    city, name, home = src["city"], src["name"], src["home"]
    info = {"city": city, "name": name, "home": home, "status": "ok", "reason": "", "count": 0}
    log("\n>>> %s  %s" % (name, home))
    home_html = fetch(home)
    if not home_html and src.get("alt"):
        log("    主页打不开，尝试备用网址：" + src["alt"])
        home = src["alt"]
        home_html = fetch(home)
        info["home"] = home
    if not home_html:
        reason = _last_err() or "首页打不开"
        log("    [失败] 首页打不开：" + reason)
        info["status"] = "fail"
        info["reason"] = reason
        return [], info

    columns = list(src.get("entries") or [])
    if not columns:
        columns = discover_columns(home_html, home)
        if columns:
            log("    自动发现栏目 %d 个：%s" % (len(columns), "；".join(c[:70] for c in columns)))
    if not columns:
        columns = [home]

    def gather(cols):
        found = []
        for col in cols[:MAX_COLUMNS]:
            for p in range(1, MAX_PAGES_PER_COLUMN + 1):
                page_url = col if p == 1 else page_url_of(col, p)
                html = home_html if page_url == home else fetch(page_url)
                if not html:
                    if p == 1:
                        log("    [跳过] 栏目打不开：" + col[:70])
                    break
                found.extend(article_links(html, page_url))
                time.sleep(0.4)
        return found

    links = gather(columns)
    # 配置的栏目全部失效时，退回首页重新自动找栏目（网站改版后的常见情况）
    if not links and src.get("entries"):
        fallback = discover_columns(home_html, home)
        if fallback and fallback != columns:
            log("    配置的栏目没抓到文章，改从首页自动发现栏目重试")
            links = gather(fallback)

    # JSON 数据接口（如深圳）
    for jurl in src.get("json_columns", []):
        links.extend(json_column_links(jurl))

    # 广东省政府信息公开平台（汕头、肇庆、汕尾、惠州等）
    gk_api_ok = False
    for base, cat in src.get("gkmlpt") or []:
        gk_links, gk_ok = gkmlpt_links(base, cat)
        links.extend(gk_links)
        gk_api_ok = gk_api_ok or gk_ok

    seen, candidates = set(), []
    for t, h in links:
        if h in seen:
            continue
        seen.add(h)
        if looks_like_recruit(t):
            candidates.append((t, h))
    log("    候选招聘公告 %d 条" % len(candidates))

    if not links:
        if gk_api_ok:
            # 接口是通的，只是没有近期文章（淡季），算 empty 不算 fail
            info["status"] = "empty"
            info["reason"] = "信息公开平台暂无近期公告"
        else:
            info["status"] = "fail"
            info["reason"] = "栏目里找不到文章链接"
        return [], info
    if not candidates:
        info["status"] = "empty"
        info["reason"] = "栏目里没有招聘类文章"
        return [], info

    jobs = []
    for t, h in candidates[:MAX_ARTICLES_PER_SOURCE]:
        job = parse_detail(h, city, name, t)
        if job:
            # 详情页标题才是完整的，再过滤一次（列表标题可能被截断而漏掉「名单」等词）
            if any(w in job["title"] for w in KEYWORD_EXCLUDE):
                log("      ✗ 非招聘公告（名单/公示类）：%s" % job["title"][:40])
            else:
                jobs.append(job)
                log("      ✓ %s" % job["title"][:50])
        time.sleep(0.4)
    log("    本条数据源抓到 %d 条" % len(jobs))

    if not jobs:
        info["status"] = "empty"
        info["reason"] = "候选公告全部被过滤（多为名单/公示类）"
    info["count"] = len(jobs)
    return jobs, info


def write_source_status(records):
    """把每个数据源的状态写进 source_status.json（给 manage.py 状态页用）"""
    prev = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f).get("sources", {})
        except Exception:
            prev = {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    stats = {}
    for rec in records:
        name = rec["name"]
        old = prev.get(name, {})
        rec["last_run"] = now
        rec["last_ok"] = old.get("last_ok", "")
        if rec.get("skipped"):
            # 本次被自动跳过的源：保留原来的连续失败次数，不再累加
            rec["fail_streak"] = int(old.get("fail_streak", 0) or 0)
        elif rec["status"] == "ok":
            rec["last_ok"] = now
            rec["fail_streak"] = 0
        elif rec["status"] == "disabled":
            rec["fail_streak"] = 0
        elif rec["status"] == "empty":
            # 源正常、只是当前没有招聘类文章（淡季常见），不算失败、不累加
            rec["last_ok"] = now
            rec["fail_streak"] = 0
        else:
            rec["fail_streak"] = int(old.get("fail_streak", 0) or 0) + 1
        rec["home"] = rec.get("home") or old.get("home", "")
        stats[name] = rec

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({"updated": now, "sources": stats}, f, ensure_ascii=False, indent=2)



def page_url_of(col, p):
    """栏目第 N 页地址：xxx/ → xxx/index_N.html"""
    if col.endswith("/"):
        return col + "index_%d.html" % p
    if col.endswith(".html") or col.endswith(".htm"):
        return re.sub(r"\.(html|htm)$", "_%d.\\1" % p, col)
    return col + "/index_%d.html" % p


def _job910_school(title):
    """从公告标题里猜学校名（如「广东建设职业技术学院2026年…招聘公告」）"""
    t = re.sub(r"^【[^】]*】", "", title).strip()
    # 开头常见的口号/引号，如「“百万英才汇南粤”行动计划清远市…」
    t = re.sub(r"^[“\"【][^”\"】]{0,24}[”\"】]", "", t)
    t = re.sub(r"^(?:百万英才汇南粤|【?百万英才汇南粤】?|粤聚英才[·•]?粤见未来|十万人才大招引)[—\-]*", "", t)
    t = re.sub(r"^行动计划[—\-]*", "", t)
    t = re.sub(r"^[^\u4e00-\u9fa5A-Za-z0-9]+", "", t)
    if "——" in t:            # 「百万英才汇南粤——2026年肇庆市…」这类宣传语
        t = t.split("——")[-1]
    parts = re.split(r"20\d{2}\s*年", t, maxsplit=1)
    if len(parts) >= 2 and parts[0].strip(" 　-—·、"):
        cand = parts[0]       # 学校名写在年份前面
    else:
        rest = parts[-1] if len(parts) >= 2 else t
        m = re.search(r"^(.{2,40}?)(?:公开|面向|统一|专项|招聘|招录|选聘|引进|诚聘|急聘|赴)", rest)
        cand = m.group(1) if m else rest
    cand = re.sub(r"（.*?）|\(.*?\)", "", cand)
    cand = re.sub(r"(?:公开)?招聘.*$|招录.*$|选聘.*$|引进.*$|公告.*$|简章.*$", "", cand)
    cand = re.sub(r"(高校毕业生|毕业生)$", "", cand)
    return cand.strip(" 　-—·、")[:45]


def _job910_city(*texts):
    blob = " ".join(x for x in texts if x)
    for c in JOB910_CITY_LIST:
        if c in blob:
            return c
    return ""


def _job910_mmdd(txt):
    """「更新于 11-09」→ 2026-11-09（没写年份，按最近一次该日期算）"""
    m = re.search(r"(\d{1,2})-(\d{1,2})", txt or "")
    if not m:
        return ""
    mo, d = int(m.group(1)), int(m.group(2))
    now = datetime.now()
    try:
        dt = datetime(now.year, mo, d)
    except ValueError:
        return ""
    if dt > now:
        try:
            dt = datetime(now.year - 1, mo, d)
        except ValueError:
            return ""
    return dt.strftime("%Y-%m-%d")


STAGE_MAP = (("幼儿园", "幼儿园"), ("小学", "小学"), ("初中", "中学"), ("高中", "中学"),
             ("中学", "中学"), ("高校", "高校"), ("大学", "高校"), ("学院", "高校"),
             ("职业", "高职"), ("高职", "高职"), ("中职", "高职"))


def _stage_of(text):
    # 「高校毕业生/应届毕业生」里的「高校」不代表招高校教师
    text = re.sub(r"(?:高校|应届|优秀)?毕业生", "", text)
    for k, v in STAGE_MAP:
        if k in text:
            return v
    return "中小学"


def _job910_private_page(html):
    """解析民办职位列表页：卡片自带职位名、学校名、城市、薪资、学段，不用再点详情"""
    s = soup_of(html)
    jobs = []
    for box in s.find_all("div", class_="content-left"):
        a = box.find("a", href=re.compile(r"jobs_view_(\d+)"))
        if not a:
            continue
        jid = re.search(r"jobs_view_(\d+)", a["href"]).group(1)
        title = (a.get("title") or a.get_text(" ", strip=True)).strip()
        if not any(k in title for k in JOB910_TEACHER_KW):
            continue
        sa = box.find("a", href=re.compile(r"school_view_"))
        school = (sa.get("title") or sa.get_text(" ", strip=True)).strip() if sa else ""
        tm = box.find("p", class_="left-time")
        date = _job910_mmdd(tm.get_text(" ", strip=True)) if tm else ""
        lis = [li.get_text(" ", strip=True) for li in box.find_all("li")]
        sal = loc = edu = exp = kind = ""
        for x in lis:
            if not sal and re.search(r"\d+(?:-\d+)?(?:\.\d+)?[KW万千]/[月年天节]", x):
                sal = x
            elif not loc and re.search(JOB910_GD_CITIES, x):
                loc = x
            elif not edu and x in ("大专", "本科", "硕士", "博士"):
                edu = x
            elif not exp and re.search(r"经验|应届|年以上|以下", x):
                exp = x
            elif not kind and ("民办" in x or "公办" in x):
                kind = x
        city = _job910_city(loc, school, title) or "广东"
        stage = _stage_of(kind + title + school)
        edu_map = {"博士": "博士", "硕士": "硕士及以上", "本科": "本科及以上", "大专": "大专及以上"}
        bits = [b for b in (
            ("薪资 " + sal) if sal else "",
            ("地点 " + loc) if loc else "",
            ("要求 " + "、".join(x for x in (edu, exp) if x)) if (edu or exp) else "",
        ) if b]
        jobs.append({
            "title": title[:80],
            "city": city,
            "school": school or "万行教师网",
            "level": "万行职位",
            "stage": stage,
            "category": "万行职位",
            "isPrivate": True,
            "establishment": "详见原文",
            "headcount": 0,
            "education": edu_map.get(edu, "详见原文"),
            "deadline": "",
            "recordedAt": date or datetime.now().strftime("%Y-%m-%d"),
            "source": "万行教师网（转载）",
            "sourceUrl": "https://www.job910.com/jobs_view_%s.html" % jid,
            "content": {
                "intro": ("；".join(bits) + "。详情请点击原文查看。") if bits else "岗位详情请点击原文查看。",
                "targets": ["以职位原文为准"],
                "positions": title[:80],
                "conditions": [x for x in (("学历 " + edu) if edu else "", ("经验 " + exp) if exp else "") if x] or ["详见原文"],
                "process": "投递简历 → 学校筛选 → 面试（通过万行教师求职版 APP 投递）",
                "signup": "在万行教师求职版 APP 在线投递，或点击原文联系招聘方",
                "contact": "详见万行教师网原文（具体信息以官方发布为准）",
            },
        })
    return jobs


def _job910_public_detail(jid):
    """解析公办公告详情页（/jobs/zhaopin-{id}.html），返回 job dict 或 None"""
    url = "https://www.job910.com/jobs/zhaopin-%s.html" % jid
    h = fetch(url, timeout=15)
    if not h:
        return None
    s = soup_of(h)
    m = re.search(r"<title>(.*?)</title>", h, re.S)
    raw = html_lib.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    raw = re.split(r"-(?:公办|民办)学校招聘", raw)[0].strip()
    raw = re.sub(r"(?:-万行教师人才网)+$", "", raw).strip()
    if not raw or not looks_like_recruit(raw):
        return None
    title = raw[:100]
    school = _job910_school(title)
    div = s.find(class_="list-content")
    body = div.get_text("\n", strip=True) if div else body_text(s)

    head_txt = s.get_text(" ", strip=True)[:2000]
    dm = re.search(r"发布时间[：:]\s*(20\d{2})-(\d{1,2})-(\d{1,2})", head_txt)
    if dm:
        date = "%04d-%02d-%02d" % (int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
    else:
        date = find_date(head_txt) or datetime.now().strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    if date > today:
        date = today

    head = 0
    for pat in (r"招聘[\u4e00-\u9fa5、（）()\s]{0,20}?(\d{1,4})\s*(?:名|人)",
                r"(?:招聘|招录|选聘)[^。]{0,15}?(\d{1,4})\s*(?:名|人)",
                r"共计?\s*(\d{1,4})\s*(?:名|人)"):
        m2 = re.search(pat, body[:3000])
        if m2:
            head = int(m2.group(1))
            break

    edu = "详见原文"
    m3 = re.search(r"(?:学历|学位)(?:要求)?[^。]{0,20}?(博士|硕士|本科|大专)", body)
    if not m3:
        m3 = re.search(r"(博士研究生|硕士研究生|本科(?:研究生)?)(?:及以上|以上)", body)
    if m3:
        v = m3.group(1)
        edu = {"博士": "博士", "博士研究生": "博士", "硕士": "硕士及以上",
               "硕士研究生": "硕士及以上", "本科": "本科及以上",
               "本科研究生": "本科及以上", "大专": "大专及以上"}.get(v, "详见原文")

    est = _guess_est(title, body)
    stage = _stage_of(title)
    if stage == "中小学":
        stage = _stage_of(body)
    # 城市以标题里的地名最准（标题「中山市翠雅学校」不能被正文里的「深圳」抢走）
    city = (_job910_city(title) or _job910_city(school)
            or _job910_city(body[:300]) or "广东")
    deadline = _extract_deadline(body, date) or _deadline_from_title(title)

    return {
        "title": title,
        "city": city,
        "school": school or "万行教师网",
        "level": "公告",
        "stage": stage,
        "category": "公办编制" if est == "正式编" else "其他",
        "establishment": est,
        "headcount": head,
        "education": edu,
        "deadline": deadline,
        "recordedAt": date,
        "source": "万行教师网（转载）",
        "sourceUrl": url,
        "content": {
            "intro": " ".join(body.split())[:160] or "详见万行教师网公告原文。",
            "targets": _extract_targets(body) or ["详见原文"],
            "positions": _extract_positions(body) or "详见原文",
            "conditions": _extract_conditions(body) or ["详见原文"],
            "process": _extract_process(body) or "详见原文",
            "signup": _extract_signup(body) or "详见原文",
            "contact": _extract_contact(body) or "详见万行教师网原文（具体信息以官方发布为准）",
        },
    }


def crawl_job910():
    """抓万行教师网的广东教师岗位（列表页 + 详情页，全自动）

    公办：/jobs/search.html?areaCode=440000&pageIndex=N 是按发布时间倒序的公告列表，
          每页 10 条；点进 /jobs/zhaopin-{id}.html 能拿到完整公告正文（学校名在标题里）。
    民办：/job/search?companyType=10&areaCode=440000&pageIndex=N 是民办学校职位列表，
          卡片自带学校名、城市、薪资、学段，不用再点详情。
    """
    log("\n>>> 万行教师网 · 列表抓取（公办公告 + 民办职位）")

    # 1) 公办公告：先从列表页收集职位 ID（已按发布时间倒序，越往后越旧）
    pub_ids = []
    for p in range(1, JOB910_PUBLIC_PAGES + 1):
        html = fetch(JOB910_PUBLIC_LIST % p, timeout=15)
        if not html:
            log("    [跳过] 公办公告第 %d 页打不开：%s" % (p, _last_err()))
            break
        got = 0
        for a in soup_of(html).find_all("a", href=re.compile(r"zhaopin-(\d+)")):
            jid = re.search(r"zhaopin-(\d+)", a["href"]).group(1)
            if jid not in pub_ids:
                pub_ids.append(jid)
                got += 1
        log("    公办公告第 %d 页：新增 %d 个（累计 %d）" % (p, got, len(pub_ids)))
        if got == 0:
            break

    pub_jobs = []
    if pub_ids:
        with ThreadPoolExecutor(max_workers=JOB910_WORKERS) as pool:
            futs = {pool.submit(_job910_public_detail, jid): jid for jid in pub_ids}
            for fu in as_completed(futs):
                r = fu.result()
                if r:
                    pub_jobs.append(r)
                    log("      ✓ [公办] %s | %s | %s" % (r["recordedAt"], r["city"], r["title"][:34]))
    log("    公办公告：解析 %d 个详情，得到 %d 条" % (len(pub_ids), len(pub_jobs)))

    # 2) 民办职位：列表卡片直接用，不点详情
    priv_jobs = []
    for p in range(1, JOB910_PRIVATE_PAGES + 1):
        html = fetch(JOB910_PRIVATE_LIST % p, timeout=15)
        if not html:
            log("    [跳过] 民办职位第 %d 页打不开：%s" % (p, _last_err()))
            break
        page_jobs = _job910_private_page(html)
        if not page_jobs:
            break
        priv_jobs.extend(page_jobs)
        log("    民办职位第 %d 页：%d 条（累计 %d）" % (p, len(page_jobs), len(priv_jobs)))
    log("    民办职位：%d 条" % len(priv_jobs))

    jobs = pub_jobs + priv_jobs
    log("    万行合计 %d 条（公办 %d / 民办 %d）" % (len(jobs), len(pub_jobs), len(priv_jobs)))
    return jobs


def load_prev_job910():
    """把上一版 data.js 里的万行岗位带过来

    万行按 ID 增量扫描，每次只扫新的一段；如果不带回旧的，
    之前扫到的职位会在下一次抓取时整批消失。
    """
    if not os.path.exists(OUT_FILE):
        return []
    try:
        txt = open(OUT_FILE, encoding="utf-8").read()
        m = re.search(r"window\.REAL_JOBS\s*=\s*(\[.*\]);", txt, re.S)
        if not m:
            return []
        old = json.loads(m.group(1))
        return [j for j in old if "万行" in j.get("source", "")]
    except Exception:
        return []


_school_db = None


def _norm_school(name):
    """校名归一化：去括号备注、去空白、去「广东省」前缀，用于跟名单库对齐"""
    s = (name or "").strip()
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    s = re.sub(r"\s|　", "", s)
    s = re.sub(r"^广东省", "", s)
    return s


def school_ownership(name):
    """查省教育厅名单，返回「公办」/「民办」；查不到返回空串"""
    global _school_db
    if _school_db is None:
        try:
            with open(SCHOOL_DB_FILE, encoding="utf-8") as f:
                _school_db = json.load(f)["schools"]
            log("    学校名单库已加载：%d 所" % len(_school_db))
        except Exception as e:
            log("    学校名单库读取失败（不影响抓取）：%s" % e)
            _school_db = {}
    s = _norm_school(name)
    if not s:
        return ""
    hit = _school_db.get(s)
    if not hit:
        hit = _school_db.get(re.sub(r"有限公司$", "", s))
    return hit[1] if hit else ""


def attach_ownership(jobs):
    """给每条公告补上公办/民办，来源是省教育厅名单而不是猜校名"""
    hit = 0
    for j in jobs:
        own = school_ownership(j.get("school", ""))
        if own:
            j["ownership"] = own
            hit += 1
    log("    公办/民办判定：%d/%d 条在名单库里查到" % (hit, len(jobs)))
    return hit


def dedupe(jobs, days_map=None):
    days_map = days_map or {}
    today = datetime.now().strftime("%Y-%m-%d")
    out, seen_url, seen_title = [], set(), set()
    # 说明：已过期/较早的公告也保留，历史招聘数据对聚合站仍有参考价值，
    #      只做 URL 与标题去重（前端可自行按 deadline 区分在招/已结束）
    for j in jobs:
        if j["sourceUrl"] in seen_url:
            continue
        key = re.sub(r"\s", "", j["title"])[:40]
        if key in seen_title:
            continue
        seen_url.add(j["sourceUrl"])
        seen_title.add(key)
        out.append(j)
    out.sort(key=lambda x: x["recordedAt"], reverse=True)
    for i, j in enumerate(out, 1):
        j["id"] = i
    return out


def main():
    start = datetime.now()
    log("=" * 56)
    log("粤师聘 · 教师招聘公告抓取  开始：%s" % start.strftime("%Y-%m-%d %H:%M:%S"))
    log("=" * 56)

    # 连续失败多次的源自动跳过，节省时间（想强制全抓：python crawler.py --all）
    force_all = "--all" in sys.argv
    prev = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f).get("sources", {})
        except Exception:
            prev = {}

    todo, skipped_records = [], []
    for src in SOURCES:
        if not src.get("enabled", True):
            skipped_records.append({
                "city": src["city"], "name": src["name"], "home": src["home"],
                "status": "disabled", "reason": "已停用", "count": 0,
            })
            continue
        streak = int(prev.get(src["name"], {}).get("fail_streak", 0) or 0)
        # 只有「网站打不开」才算失效；「抓到 0 条」只是暂时没新公告，照常抓取
        was_fail = prev.get(src["name"], {}).get("status") == "fail"
        if not force_all and was_fail and streak >= SKIP_FAIL_STREAK:
            skipped_records.append({
                "city": src["city"], "name": src["name"], "home": src["home"],
                "status": "fail", "count": 0, "skipped": True,
                "reason": "连续失败 %d 次，本次自动跳过（点「体检数据源」可复查）" % streak,
            })
        else:
            todo.append(src)
    if skipped_records:
        log("自动跳过 %d 个源（连续失效或已停用）" % len(skipped_records))
    log("实际抓取 %d 个源，%d 个并行\n" % (len(todo), WORKERS))

    all_jobs = []
    source_records = list(skipped_records)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(crawl_source, src): src for src in todo}
        for fu in as_completed(futures):
            src = futures[fu]
            try:
                jobs, info = fu.result()
            except Exception as e:
                log("    [异常] %s：%s" % (src["name"], e))
                jobs = []
                info = {
                    "city": src["city"], "name": src["name"], "home": src["home"],
                    "status": "fail", "reason": "程序异常：%s" % e, "count": 0,
                }
            all_jobs.extend(jobs)
            source_records.append(info)

    # ===== 第三方源：万行教师网（转载，来源如实标注）=====
    try:
        job910_jobs = crawl_job910()
        all_jobs.extend(job910_jobs)
    except Exception as e:
        log("\n[异常] 万行扫描失败：%s" % e)

    # 高校官网 · 各校「人才招聘 / 人事处」栏目（一手官方源）
    try:
        import uni_sources
        uni_sources.set_logger(log)
        all_jobs.extend(uni_sources.crawl_universities())
    except Exception as e:
        log("\n[异常] 高校官网源失败：%s" % e)

    # 带回上一版的万行岗位（万行按 ID 增量扫描，不带回旧的会整批消失）
    prev_job910 = load_prev_job910()
    if prev_job910:
        log("    带回上一版万行岗位 %d 条" % len(prev_job910))
        all_jobs.extend(prev_job910)

    days = {s["name"]: (PRIVATE_RECENT_DAYS if "民办" in s["name"] else RECENT_DAYS)
            for s in SOURCES}

    # === DEBUG: dedupe 前看 6 城 ===
    debug_cities = ["珠海", "河源", "潮州", "揭阳", "阳江", "梅州"]
    debug_before = [j for j in all_jobs if any(c in j.get("title","") + j.get("school","") + j.get("city","") for c in debug_cities)]
    debug_before_prf = [j for j in debug_before if not j.get("pendingReview")]
    log(f"    [DEBUG] dedupe 前 6 城条目: {len(debug_before)} (其中 pr=False 公办: {len(debug_before_prf)})")
    for j in debug_before_prf:
        log(f"      ✅公办 city={j.get('city')} src={j.get('source','')[:25]} dead={j.get('deadline')} rec={j.get('recordedAt')} title={j.get('title','')[:45]}")

    jobs = dedupe(all_jobs, days)

    debug_after = [j for j in jobs if any(c in j.get("title","") + j.get("school","") + j.get("city","") for c in debug_cities)]
    debug_after_prf = [j for j in debug_after if not j.get("pendingReview")]
    log(f"    [DEBUG] dedupe 后 6 城条目: {len(debug_after)} (其中 pr=False 公办: {len(debug_after_prf)})")
    for j in debug_after_prf:
        log(f"      ✅公办 city={j.get('city')} src={j.get('source','')[:25]} title={j.get('title','')[:45]}")

    attach_ownership(jobs)

    out_lines = [
        "// 本文件由 crawler/crawler.py 自动生成，请勿手工修改\n",
        "// 生成时间：%s   共 %d 条\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(jobs)),
        "window.DATA_UPDATED = \"%s\";\n" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "window.REAL_JOBS = " + json.dumps(jobs, ensure_ascii=False, indent=2) + ";\n",
        "if (window.REAL_JOBS && window.REAL_JOBS.length) { MOCK_JOBS = window.REAL_JOBS; }\n",
    ]
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(out_lines)
    os.replace(tmp, OUT_FILE)

    write_source_status(source_records)

    # 第三方来源（万行）的条目不上线，单独导出一份核验清单：按学校名去官网找原文
    pending = [j for j in jobs if j.get("pendingReview")]
    if pending:
        pend_file = os.path.join(BASE_DIR, "pending_review.json")
        with open(pend_file, "w", encoding="utf-8") as f:
            json.dump([{k: j.get(k, "") for k in
                        ("school", "city", "stage", "title", "sourceUrl", "recordedAt")}
                       for j in pending], f, ensure_ascii=False, indent=2)
        log("待核验 %d 条（第三方来源，页面不展示）：%s" % (len(pending), pend_file))
    ok_n = sum(1 for r in source_records if r["status"] == "ok")
    empty_n = sum(1 for r in source_records if r["status"] == "empty")
    fail_n = sum(1 for r in source_records if r["status"] == "fail")
    log("数据源情况：正常 %d 个，抓到 0 条 %d 个，失效 %d 个" % (ok_n, empty_n, fail_n))
    log("（想看完整表格，关掉本窗口后双击「一键运行.bat」，选 2）")

    log("=" * 56)
    log("完成：共 %d 条真实公告" % len(jobs))
    log("数据文件：" + os.path.abspath(OUT_FILE))
    log("耗时：%.1f 秒" % (datetime.now() - start).total_seconds())

    with open(LOG_FILE, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(_log_lines))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("已手动中断")
        sys.exit(0)
