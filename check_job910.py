import re, json

content = open(r'F:\XIANG\粤教师\粤教职圈\crawler\data_anns.js.bak', encoding='utf-8').read()
m = re.search(r'window\.REAL_JOBS\s*=\s*(\[.*\]);', content, re.S)
jobs = json.loads(m.group(1))

job910 = [j for j in jobs if "万行" in j.get("source", "") or "job910" in j.get("sourceUrl", "")]
print("万行 records:", len(job910))
if job910:
    j = job910[0]
    print("source:", j.get("source"))
    print("sourceUrl:", j.get("sourceUrl"))
    print("pendingReview:", j.get("pendingReview"))
    print("title:", j.get("title"))
    print("has id:", "id" in j, j.get("id"))
