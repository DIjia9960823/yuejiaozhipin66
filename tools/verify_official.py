# -*- coding: utf-8 -*-
"""上线前硬检查：data_anns.js 里只要有一条第三方链接，直接失败。"""
import re
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from official_rule import is_official

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raw = open(os.path.join(ROOT, "crawler", "data_anns.js"), encoding="utf-8").read()
jobs = json.loads(re.search(r'window\.REAL_JOBS\s*=\s*(\[.*\]);', raw, re.S).group(1))

bad = [j for j in jobs if not is_official(j.get("sourceUrl", ""), j.get("source", ""))]
print("公告总数:", len(jobs))
print("第三方链接:", len(bad))
for j in bad[:5]:
    print("  ✗", j.get("source"), j.get("sourceUrl"))

if bad:
    print("❌ 有第三方链接混入，流水线中止")
    sys.exit(1)
print("✅ 全部是官方原文")
