# -*- coding: utf-8 -*-
"""把系统临时目录里的 sydw_added.json 合并进 data_anns.js"""
import re, json, os, tempfile

DATA = r'F:\XIANG\粤教师\粤教职圈\crawler\data_anns.js'
ADDED = os.path.join(tempfile.gettempdir(), "sydw_added.json")

if not os.path.exists(ADDED):
    print("no sydw_added.json found"); exit(1)

raw = open(DATA, encoding='utf-8').read()
m = re.search(r'window\.REAL_JOBS\s*=\s*(\[.*\]);', raw, re.S)
existing = json.loads(m.group(1))

added = json.load(open(ADDED, encoding='utf-8'))
seen_urls = {j.get("sourceUrl", "").rstrip("/") for j in existing}
new = [j for j in added if j.get("sourceUrl", "").rstrip("/") not in seen_urls]

print("existing: %d, added file: %d, actually new: %d" % (len(existing), len(added), len(new)))

merged = existing + new
new_json = json.dumps(merged, ensure_ascii=False, indent=2)
header = raw[:m.start(1)]
footer = raw[m.end(1):]
header = re.sub(r"共 \d+ 条", "共 %d 条" % len(merged), header)

tmp = DATA + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(header + new_json + footer)
os.replace(tmp, DATA)
print("done. total:", len(merged))
