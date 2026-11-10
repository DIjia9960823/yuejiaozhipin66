# -*- coding: utf-8 -*-
"""把 data_anns.js.bak 里的万行教师网记录恢复进 data_anns.js，
并按用户要求把来源标成「万行教师网（转载）」、去掉 pendingReview。"""
import re, json
from datetime import datetime

DATA = r'F:\XIANG\粤教师\粤教职圈\crawler\data_anns.js'
BAK = r'F:\XIANG\粤教师\粤教职圈\crawler\data_anns.js.bak'

def load(path):
    raw = open(path, encoding='utf-8').read()
    m = re.search(r'window\.REAL_JOBS\s*=\s*(\[.*\]);', raw, re.S)
    return raw, m, json.loads(m.group(1))

raw_cur, m_cur, current = load(DATA)
_, _, bak = load(BAK)

job910 = [j for j in bak if "万行" in j.get("source", "") or "job910" in j.get("sourceUrl", "")]

cur_urls = {j.get("sourceUrl", "").rstrip("/") for j in current}
to_add = []
for j in job910:
    if j.get("sourceUrl", "").rstrip("/") in cur_urls:
        continue
    j = dict(j)
    j["source"] = "万行教师网（转载）"
    j.pop("pendingReview", None)
    to_add.append(j)

print("current: %d, bak 万行: %d, 新增: %d" % (len(current), len(job910), len(to_add)))

merged = current + to_add
new_json = json.dumps(merged, ensure_ascii=False, indent=2)

# 保留原文件头（前3行注释+DATA_UPDATED），只替换 REAL_JOBS 数组
header = raw_cur[:m_cur.start(1)]
footer = raw_cur[m_cur.end(1):]

# 更新注释里的条数
header = re.sub(r"共 \d+ 条", "共 %d 条" % len(merged), header)
header = re.sub(r"生成时间：[^\n]*", "生成时间：%s   共 %d 条" % (
    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), len(merged)), header)

out = header + new_json + footer
with open(DATA, "w", encoding="utf-8") as f:
    f.write(out)

print("done. data_anns.js now has %d records" % len(merged))
