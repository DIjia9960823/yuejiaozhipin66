import re
from collections import Counter

content = open(r'F:\XIANG\粤教师\粤教职圈\crawler\data_anns.js.bak2', encoding='utf-8').read()
jobs = re.findall(r'"source":\s*"([^"]+)"', content)
c = Counter(jobs)
print('total:', len(jobs))
for k, v in c.most_common():
    print(f'{k}: {v}')
