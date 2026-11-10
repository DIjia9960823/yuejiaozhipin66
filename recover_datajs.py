# -*- coding: utf-8 -*-
"""从临时目录恢复 positions_all.json，并生成 data.js"""
import json, os, tempfile, shutil

BASE = r'F:\XIANG\粤教师\粤教职圈\tools'
ROOT = r'F:\XIANG\粤教师\粤教职圈'

src = os.path.join(tempfile.gettempdir(), "positions_all.json")
dst = os.path.join(BASE, "positions_all.json")
shutil.copy2(src, dst)
print("copied positions_all.json")

positions = json.load(open(dst, encoding='utf-8'))
print("total positions:", len(positions))

out = "window.POSITIONS=" + json.dumps(positions, ensure_ascii=False, separators=(",", ":")) + ";"
data_js = os.path.join(ROOT, "data.js")
tmp = data_js + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(out)
os.replace(tmp, data_js)
print("data.js written:", os.path.getsize(data_js), "bytes")

# Also copy skipped_dead if exists
src_dead = os.path.join(tempfile.gettempdir(), "skipped_dead.json")
if os.path.exists(src_dead):
    shutil.copy2(src_dead, os.path.join(BASE, "skipped_dead.json"))
    print("copied skipped_dead.json")
