# -*- coding: utf-8 -*-
"""
粤教职圈 · 公告拆职位工具
作用：读取粤师聘 data.js 里的官方公告，打开每份公告原文页，
     下载《岗位表》附件（xls/xlsx/zip/pdf），把每行岗位拆成一条职位。
铁规矩：只处理官方来源；解析不了就记入 skipped.json，绝不编造数据。
输入：F:\\XIANG\\粤教师\\粤师聘-原型\\guangdong-teacher-jobs\\data.js
输出：本目录下 positions.json（职位列表）、skipped.json（跳过清单）
"""
import json, re, os, io, zipfile, sys
import requests
try:
    import truststore  # Windows 上注入系统证书链，Linux 不需要
    truststore.inject_into_ssl()
except ImportError:
    pass  # Linux Actions 环境自动跳过
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# 优先读 crawler/ 目录下的最新公告列表（自动爬取输出），
# 没有就回退到根目录 data.js（旧版兼容）
_DATA_NEW = os.path.join(ROOT, "crawler", "data_anns.js")
_DATA_OLD = os.path.join(ROOT, "data.js")
if os.path.exists(_DATA_NEW) and os.path.getsize(_DATA_NEW) > 500:
    DATA_JS = _DATA_NEW
else:
    DATA_JS = _DATA_OLD
ATT_DIR = os.path.join(BASE, "附件缓存")
os.makedirs(ATT_DIR, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT = 30

# 附件文件名里带这些词才认为是岗位表；带「报名表/目录/承诺书」等跳过
ATT_WANT = ["岗位", "职位", "需求表", "一览表", "计划表"]
ATT_SKIP = ["报名表", "目录", "承诺书", "同意书", "证明", "简历", "登记表",
            "体检", "考察表", "成绩", "名单", "公示", "准考证", "须知", "指南",
            "资格审查", "业绩", "成果", "初检", "报名教程",
            "专业参考", "专业目录", "考试录用公务员"]

# 表头列名同义词
COL_MAP = {
    "school": ["单位名称", "用人单位", "招聘单位", "工作部门", "学校名称", "招聘单位名称", "招聘部门", "单位"],
    "job":    ["岗位名称", "职位名称", "招聘岗位", "岗位", "学科", "职位"],
    "code":   ["职位代码", "岗位代码", "岗位编号", "职位编号", "代码"],
    "num":    ["拟聘人数", "招聘人数", "人数", "计划招聘", "需求人数", "招聘数量", "计划数", "数量"],
    "edu":    ["学历要求", "学历", "最低学历"],
    "degree": ["学位要求", "学位"],
    "major":  ["专业名称及代码", "专业要求", "专业及代码", "相关专业", "需求专业", "所学专业"],
    "other":  ["其它要求", "其他要求", "备注", "年龄", "职称", "招聘对象", "岗位等级",
               "考试方式", "岗位职责", "资格", "要求", "联系方式"],
}


def load_announcements():
    s = open(DATA_JS, encoding="utf-8").read()
    i = s.index("[")
    jobs, _ = json.JSONDecoder().raw_decode(s[i:])
    return [j for j in jobs if not j.get("pendingReview")]


def find_attachments(page_url):
    """打开公告页，返回 [(附件名, 绝对url)]，只保留像岗位表的"""
    r = requests.get(page_url, timeout=TIMEOUT, headers=UA)
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        h, t = a["href"].strip(), a.get_text(strip=True)
        low = h.lower()
        if not any(x in low for x in [".xls", ".xlsx", ".pdf", ".zip", ".doc", ".docx"]):
            continue
        name = t or os.path.basename(h)
        if any(k in name for k in ATT_SKIP):
            continue
        if not any(k in name for k in ATT_WANT) and "attachment" not in low:
            # 文件名看不出是岗位表、也不是通用附件路径的，跳过
            continue
        if h.startswith("/"):
            m = re.match(r"(https?://[^/]+)", page_url)
            h = m.group(1) + h
        elif not h.startswith("http"):
            h = page_url.rsplit("/", 1)[0] + "/" + h
        out.append((name, h))
    return out


def clean(v):
    s = re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""
    if re.fullmatch(r"\d+\.0", s):  # Excel 数字读出来是 2.0，变回 2
        s = s[:-2]
    return s


def read_table(path):
    """读 xls/xlsx，返回 [[cell,...],...]；多个工作表合并"""
    rows = []
    if path.lower().endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        for sn in wb.sheetnames:
            ws = wb[sn]
            for r in ws.iter_rows(values_only=True):
                rows.append([clean(c) for c in r])
    elif path.lower().endswith(".xls"):
        head = open(path, "rb").read(8)
        if head.startswith(b"<?xml") or head.lstrip().startswith(b"<"):
            rows = read_spreadsheetml(path)  # 伪装成 .xls 的 XML 表格
        else:
            import xlrd
            wb = xlrd.open_workbook(path)
            for sh in wb.sheets():
                for i in range(sh.nrows):
                    rows.append([clean(sh.cell_value(i, j)) for j in range(sh.ncols)])
    return rows


def read_spreadsheetml(path):
    """解析 SpreadsheetML（XML 版 Excel）：按 Row/Cell/Data 标签抽数据"""
    import xml.etree.ElementTree as ET
    tree = ET.parse(path)
    rows = []
    for row in tree.iter():
        if not row.tag.endswith("Row"):
            continue
        cells = []
        for cell in row:
            if not cell.tag.endswith("Cell"):
                continue
            txt = "".join(d.text or "" for d in cell.iter() if d.tag.endswith("Data"))
            cells.append(clean(txt))
        if cells:
            rows.append(cells)
    return rows


def read_word(path):
    """读 Word 附件：按文件头判断真实格式（政府网站的 .doc 常是 HTML 或 docx 伪装）"""
    head = open(path, "rb").read(512)
    if head[:2] == b"PK":                      # zip 容器 -> 其实是 docx
        return read_docx(path)
    stripped = head.lstrip(b"\xef\xbb\xbf\xff\xfe \t\r\n")
    if stripped[:1] == b"<":                   # HTML 伪装的 .doc
        return read_html_table(path)
    if head[:5] == b"{\\rtf":
        raise ValueError("RTF 格式的 doc 暂不支持")
    if head[:4] == b"\xd0\xcf\x11\xe0":
        raise ValueError("老二进制 doc 暂不支持")
    return read_html_table(path)               # 未知格式，最后按 HTML 试一次


def read_docx(path):
    """python-docx 读 docx 里的所有表格"""
    import docx
    d = docx.Document(path)
    rows = []
    for tbl in d.tables:
        for r in tbl.rows:
            rows.append([clean(c.text) for c in r.cells])
    return rows


def read_html_table(path):
    """解析 HTML 文件里的 <table>（伪 .doc 常见于此）"""
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "ignore")
    soup = BeautifulSoup(text, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = [clean(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    return rows


def parse_pdf_table(path):
    """用 pdfplumber 抽 PDF 表格，返回行列表"""
    import pdfplumber
    rows = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            for tbl in (pg.extract_tables() or []):
                for r in tbl:
                    rows.append([clean(c) for c in r])
    return rows


def match_col(header_cell):
    """表头单元格 -> 字段名；取最长的同义词匹配（避免「岗位代码」被当成「岗位」）"""
    h = header_cell.replace(" ", "")
    best, best_len = None, 0
    for field, words in COL_MAP.items():
        if field == "job" and ("条件" in h or "要求" in h):
            continue  # 「招聘岗位条件」「应聘岗位要求」不是岗位名列
        for w in words:
            if w in h and len(w) > best_len:
                best, best_len = field, len(w)
    return best


def header_score(row):
    return sum(1 for c in row if c and match_col(c))


def rows_to_positions(rows):
    """通用表格解析：找表头行 -> 映射列 -> 逐行出职位"""
    # 表头块：第一行 score>=3 起，后面紧挨的 score>=2 的行也算表头（处理两层表头）
    hi = -1
    for i, r in enumerate(rows[:10]):
        if header_score(r) >= 3:
            hi = i
            break
    if hi < 0:
        return []
    end = hi
    while end + 1 < len(rows):
        nxt = rows[end + 1]
        # 子表头特征：不含序号数字；一旦某行前两格出现纯数字（序号），说明数据开始了
        if header_score(nxt) < 3 or any(re.fullmatch(r"\d+", c) for c in nxt[:2]):
            break
        end += 1
    # 合并表头块：下层优先，空格子用上层补（如「招聘岗位条件」下分学历/专业/年龄）
    header = list(rows[hi])
    for r in rows[hi + 1:end + 1]:
        header = [(r[c] if c < len(r) and r[c] else h) for c, h in enumerate(header)]
    # 合并表头：空表头继承左边（处理「专业及代码」跨两列）
    filled, last = [], ""
    for h in header:
        if h:
            last = h
        filled.append(h or last)
    # 记录字段->列号（一个字段可多列）
    field_cols = {}
    for idx, h in enumerate(filled):
        f = match_col(h)
        if f:
            field_cols.setdefault(f, []).append(idx)

    positions = []
    school_ff = ""
    for r in rows[end + 1:]:
        def get(field):
            vals = [r[c] for c in field_cols.get(field, []) if c < len(r) and r[c]]
            return "；".join(dict.fromkeys(vals))
        school = get("school")
        if school:
            school_ff = school
        else:
            school = school_ff
        job, code = get("job"), get("code")
        if not job or job in ("岗位名称", "职位名称"):
            continue
        if job in ("合计", "小计") or "合计" == job.strip():
            continue
        positions.append({
            "school": school, "job": job, "code": code,
            "num": get("num"), "edu": get("edu"), "degree": get("degree"),
            "major": get("major"), "other": get("other"),
        })
    return positions


def guess_establishment(ann):
    """编制性质：公告标题写了「非事业编制/项目制/编外」等，以标题为准（data.js 里的值有错）"""
    t = ann.get("title", "")
    if any(k in t for k in ["非事业编制", "非编", "编外", "项目制", "合同制", "劳务派遣", "临聘", "聘用制"]):
        return "合同制"
    if any(k in t for k in ["事业编制", "编制内", "正式编制"]):
        return "正式编"
    return ann.get("establishment", "")


def guess_stage(school, job, ann_stage):
    text = school + job
    if "幼儿园" in text or "幼儿教师" in text:
        return "幼儿园"
    if "小学" in text:
        return "小学"
    if "高中" in text:
        return "高中"
    if "初中" in text:
        return "初中"
    if any(k in text for k in ["大学", "学院", "高等专科"]):
        return "高校"
    if "中职" in text or "中等职业" in text or "技工" in text:
        return "中职"
    if "中学" in text:
        return "中学"
    return ann_stage or ""


def download(url, save_name):
    p = os.path.join(ATT_DIR, save_name)
    if not os.path.exists(p):
        r = requests.get(url, timeout=60, headers=UA)
        r.raise_for_status()
        open(p, "wb").write(r.content)
    return p


def process(ann):
    """处理一条公告，返回 (职位列表, 跳过原因 or None)"""
    url = ann.get("sourceUrl", "")
    if not url:
        return [], "没有公告链接"
    try:
        atts = find_attachments(url)
    except Exception as e:
        return [], f"公告页打不开: {type(e).__name__}"
    if not atts:
        return [], "页面没有岗位表附件"
    all_pos = []
    errs = []
    for name, aurl in atts:
        try:
            safe = re.sub(r'[\\/:*?"<>|]', "_", f"{ann['id']}_{name}")
            safe = re.sub(r"\.(xls|xlsx|pdf|zip|doc|docx)$", "", safe, flags=re.I)[:70]  # 先去掉旧扩展名再截断
            path_part = aurl.lower().split("?")[0]  # 去掉查询参数
            EXTS = (".zip", ".xls", ".xlsx", ".doc", ".docx", ".pdf")
            if not path_part.endswith(EXTS):
                # URL 扩展名藏在 query 参数里（如 .gzsport 的 ?filepath=xxx.xls），从附件名兜底
                for ex in EXTS:
                    if name.lower().endswith(ex):
                        path_part = ex
                        break
            if path_part.endswith(".zip"):
                zp = download(aurl, safe + ".zip")
                z = zipfile.ZipFile(zp)
                for n in z.namelist():
                    try:
                        inner = n.encode("cp437").decode("gbk")
                    except Exception:
                        inner = n
                    if any(k in inner for k in ATT_SKIP):
                        continue
                    if not any(k in inner for k in ATT_WANT):
                        continue
                    if not inner.lower().endswith((".xls", ".xlsx", ".doc", ".docx")):
                        continue
                    ip = os.path.join(ATT_DIR, safe + "_" + re.sub(r'[\\/:*?"<>|]', "_", inner))
                    if not os.path.exists(ip):
                        open(ip, "wb").write(z.read(n))
                    if inner.lower().endswith((".doc", ".docx")):
                        all_pos += rows_to_positions(read_word(ip))
                    else:
                        all_pos += rows_to_positions(read_table(ip))
            elif path_part.endswith((".xls", ".xlsx")):
                ext = ".xlsx" if path_part.endswith(".xlsx") else ".xls"
                p = download(aurl, safe + ext)
                all_pos += rows_to_positions(read_table(p))
            elif path_part.endswith((".doc", ".docx")):
                ext = ".docx" if path_part.endswith(".docx") else ".doc"
                p = download(aurl, safe + ext)
                all_pos += rows_to_positions(read_word(p))
            elif path_part.endswith(".pdf"):
                p = download(aurl, safe + ".pdf")
                all_pos += rows_to_positions(parse_pdf_table(p))
        except Exception as e:
            errs.append(f"{name[:30]}: {type(e).__name__}")
    if not all_pos:
        return [], "附件解析不出岗位" + ("; " + "; ".join(errs) if errs else "")
    # 补公共字段
    ann_school = ann.get("school", "")
    for p in all_pos:
        if not p["school"]:
            p["school"] = ann_school
        elif (ann_school and ann_school not in p["school"]
              and any(k in ann_school for k in ["大学", "学院", "学校"])):
            p["school"] = ann_school + "·" + p["school"]  # 高校里的二级学院，带上学校名
        p["stage"] = guess_stage(p["school"], p["job"], ann.get("stage", ""))
        p["city"] = fix_city(p["school"], ann.get("title", ""), ann.get("city", ""))
        p["establishment"] = guess_establishment(ann)
        p["deadline"] = ann.get("deadline", "")
        p["recordedAt"] = ann.get("recordedAt", "")
        p["annTitle"] = ann.get("title", "")
        p["sourceUrl"] = url
    return all_pos, None


# 学校名关键字 -> 所在城市（手工核对，省属学校公告 city 字段常是"广东"，靠这个兜底）
SCHOOL_CITY = {
    "松山职业技术学院": "韶关",
    "惠州学院": "惠州",
    "水利电力职业技术学院": "广州",
    "建设职业技术学院": "广州",
    "交通职业技术学院": "广州",
    "药科大学": "广州",
    "体育学院": "广州",
    "广东工业大学": "广州",
    "南方医科大学": "广州",
    "华南农业大学": "广州",
    "广东第二师范学院": "广州",
    "广东技术师范大学": "广州",
    "广东财经大学": "广州",
    "华南理工大学": "广州",
    "广东海洋大学": "湛江",
}
GD_CITIES = ["广州", "深圳", "珠海", "汕头", "佛山", "韶关", "河源", "梅州", "惠州",
             "汕尾", "东莞", "中山", "江门", "阳江", "湛江", "茂名", "肇庆", "清远",
             "潮州", "揭阳", "云浮"]

def fix_city(school, ann_title, ann_city):
    """优先学校名关键字，其次公告标题里的城市名，最后才信公告原 city 字段。"""
    text = (school or "") + " " + (ann_title or "")
    for k, v in SCHOOL_CITY.items():
        if k in text:
            return v
    for c in GD_CITIES:
        if c in text:
            return c
    c = (ann_city or "").replace("市", "")
    return c if c in GD_CITIES else ""


def dump_json(obj, path, tries=15):
    """写 JSON，被别的程序（如 WPS/杀毒）临时占用时自动重试。
    先写 .tmp 再 os.replace，比直接覆盖更不容易被锁。"""
    import time, tempfile
    # 先在系统临时目录存一份保底，防止写项目目录失败导致数据全丢
    backup = os.path.join(tempfile.gettempdir(), os.path.basename(path))
    json.dump(obj, open(backup, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tmp = path + ".tmp"
    for i in range(tries):
        try:
            json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            print(f"  {os.path.basename(path)} 被占用，3秒后重试 ({i+1}/{tries})...")
            time.sleep(3)


def main():
    anns = load_announcements()
    # 第三方转载页（万行/公考雷达等）不会有官方岗位表附件，跳过附件解析，
    # 它们会在 ann_to_positions.py 里转成公告级职位。
    official = [a for a in anns if "转载" not in a.get("source", "")]
    third_party = len(anns) - len(official)
    print(f"可见公告 {len(anns)} 条（官方 {len(official)} / 转载 {third_party}），开始拆职位...")
    positions, skipped = [], []
    with ThreadPoolExecutor(6) as ex:
        for ann, (pos, reason) in zip(official, ex.map(process, official)):
            if pos:
                positions += pos
                print(f"  [OK {len(pos):>4}] {ann['title'][:38]} -> {len(pos)} 条职位")
            else:
                skipped.append({"id": ann["id"], "title": ann["title"],
                                "sourceUrl": ann.get("sourceUrl", ""), "reason": reason})
                print(f"  [跳过] {ann['title'][:38]} : {reason}")
    # 职位编号
    for i, p in enumerate(positions, 1):
        p["id"] = i
    dump_json(positions, os.path.join(BASE, "positions_out.json"))
    dump_json(skipped, os.path.join(BASE, "skipped_out.json"))
    print(f"\n完成：{len(positions)} 条职位（来自 {len(official)-len(skipped)} 份公告），跳过 {len(skipped)} 份")


if __name__ == "__main__":
    main()
