# -*- coding: utf-8 -*-
"""调查：skipped.json 中"页面没有岗位表附件"的公告页，有多少挂了 .doc/.docx 附件"""
import json, re, os
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import truststore
truststore.inject_into_ssl()

BASE = os.path.dirname(os.path.abspath(__file__))
skipped = json.load(open(os.path.join(BASE, 'skipped.json'), encoding='utf-8'))
targets = [x for x in skipped if x.get('reason') == '页面没有岗位表附件']

# 链接里出现 doc/docx 即算（附件通常是 href=...docx 或带下载参数）
DOC_RE = re.compile(r'\.docx?(?:\?|"|\'|\s|$)', re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+\.docx?(?:\?[^"\']*)?)["\']', re.I)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def check(item):
    url = item.get('sourceUrl', '')
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        r.encoding = r.apparent_encoding or 'utf-8'
        html = r.text
        links = HREF_RE.findall(html)
        return {'url': url, 'title': item.get('annTitle', '')[:40], 'status': r.status_code,
                'doc_links': links[:5], 'has_doc': bool(links)}
    except Exception as e:
        return {'url': url, 'title': item.get('annTitle', '')[:40], 'status': 'ERR',
                'doc_links': [], 'has_doc': False, 'err': str(e)[:80]}

import urllib3
urllib3.disable_warnings()

results = []
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(check, t): t for t in targets}
    for i, f in enumerate(as_completed(futs), 1):
        results.append(f.result())
        if i % 30 == 0:
            print(f'进度 {i}/{len(targets)}', flush=True)

has = [r for r in results if r['has_doc']]
err = [r for r in results if r['status'] == 'ERR']
dead = [r for r in results if isinstance(r['status'], int) and r['status'] >= 400]
print(f"\n=== 调查完成 ===")
print(f"总公告数: {len(results)}")
print(f"有 Word 附件: {len(has)}")
print(f"访问出错: {len(err)}")
print(f"页面打不开(4xx/5xx): {len(dead)}")
print(f"确实没有 Word 附件: {len(results) - len(has) - len(err) - len(dead)}")

json.dump(results, open(os.path.join(BASE, 'word_check.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print("\n有 Word 附件的前 10 条示例:")
for r in has[:10]:
    print(' -', r['title'], '|', r['doc_links'][0] if r['doc_links'] else '')
print("\n结果已存 word_check.json")
