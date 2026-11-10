import re, json
from collections import Counter

content = open(r'F:\XIANG\粤教师\粤教职圈\crawler\data_anns.js', encoding='utf-8').read()
m = re.search(r'window\.REAL_JOBS\s*=\s*(\[.*\]);', content, re.S)
jobs = json.loads(m.group(1))

sources = Counter(j.get("source", "") for j in jobs)
print("total:", len(jobs))
for k, v in sources.most_common():
    print(f'{k}: {v}')

# Check pendingReview count
pr = sum(1 for j in jobs if j.get("pendingReview"))
print("pendingReview:", pr)
