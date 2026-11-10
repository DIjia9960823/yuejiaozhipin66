import re, json

# Read current data_anns.js
cur_content = open(r'F:\XIANG\粤教师\粤教职圈\crawler\data_anns.js', encoding='utf-8').read()
m = re.search(r'window\.REAL_JOBS\s*=\s*(\[.*\]);', cur_content, re.S)
current = json.loads(m.group(1))
print("current:", len(current))

# Read bak
bak_content = open(r'F:\XIANG\粤教师\粤教职圈\crawler\data_anns.js.bak', encoding='utf-8').read()
m2 = re.search(r'window\.REAL_JOBS\s*=\s*(\[.*\]);', bak_content, re.S)
bak = json.loads(m2.group(1))

job910 = [j for j in bak if "万行" in j.get("source", "") or "job910" in j.get("sourceUrl", "")]
print("bak 万行:", len(job910))

# Check ID overlap
cur_ids = {j.get("id") for j in current}
bak_ids = {j.get("id") for j in job910}
overlap = cur_ids & bak_ids
print("ID overlap:", len(overlap))
if overlap:
    print("sample overlap:", list(overlap)[:5])

# Check sourceUrl overlap
cur_urls = {j.get("sourceUrl", "").rstrip("/") for j in current}
dup_urls = [j for j in job910 if j.get("sourceUrl", "").rstrip("/") in cur_urls]
print("sourceUrl overlap (万行 already in current):", len(dup_urls))

# Max id in current
max_cur_id = max(cur_ids) if cur_ids else 0
print("max current id:", max_cur_id)
max_bak_id = max(bak_ids) if bak_ids else 0
print("max bak id:", max_bak_id)
