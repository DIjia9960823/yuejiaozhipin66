# -*- coding: utf-8 -*-
"""把没拆出岗位表的官方公告，转成"公告级职位"（一份公告 = 一个职位）。
跑完会和 positions.json 里已有的职位合并，重新编号，生成网站用的 data.js。"""
import json, os, re, sys, collections
from concurrent.futures import ThreadPoolExecutor
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_positions import load_announcements, fix_city, UA, TIMEOUT

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)


def alive(url):
    """公告链接现在能不能打开。打不开的不能上线。"""
    try:
        r = requests.get(url, timeout=TIMEOUT, headers=UA, stream=True)
        r.close()
        return r.status_code < 400
    except Exception:
        return False


def ann_to_position(ann):
    c = ann.get("content") or {}
    other = "该公告未附岗位明细表，岗位详情见公告原文"
    if c.get("contact"):
        other += "；联系方式：" + c["contact"]
    school = ann.get("school") or re.sub(r"(公告|启事)$", "", ann["title"])
    return {
        "school": school,
        "job": ann["title"],
        "code": "",
        "num": str(ann.get("headcount") or ""),
        "edu": ann.get("education", ""),
        "degree": "",
        "major": "",
        "other": other,
        "stage": ann.get("stage", ""),
        "city": fix_city(school, ann["title"], ann.get("city", "")),
        "establishment": ann.get("establishment", ""),
        "deadline": ann.get("deadline", ""),
        "annTitle": ann["title"],
        "sourceUrl": ann["sourceUrl"],
    }


def main():
    positions = json.load(open(os.path.join(BASE, "positions_out.json"), encoding="utf-8"))
    covered = set(p["sourceUrl"] for p in positions)

    anns = load_announcements()  # 已过滤掉万行等 pendingReview 的数据
    # 双保险：来源链接/来源名绝不允许出现第三方
    anns = [a for a in anns if "job910" not in a.get("sourceUrl", "")
            and "万行" not in (a.get("source", "") + a.get("title", ""))]

    todo, seen = [], set()
    for a in anns:
        u = a.get("sourceUrl", "")
        if not u or u in covered or u in seen:
            continue
        seen.add(u)
        todo.append(a)
    print(f"已有职位覆盖 {len(covered)} 份公告；待转公告级职位 {len(todo)} 份")

    # 检查链接死活，死链不上线
    dead = []
    with ThreadPoolExecutor(8) as ex:
        for a, ok in zip(todo, ex.map(lambda x: alive(x["sourceUrl"]), todo)):
            if not ok:
                dead.append({"title": a["title"], "sourceUrl": a["sourceUrl"]})
    live = [a for a in todo if all(a["sourceUrl"] != d["sourceUrl"] for d in dead)]
    print(f"链接打不开的 {len(dead)} 份（已跳过，存 skipped_dead.json）")

    new_positions = [ann_to_position(a) for a in live]
    all_positions = positions + new_positions
    for i, p in enumerate(all_positions, 1):
        p["id"] = i

    json.dump(all_positions, open(os.path.join(BASE, "positions_all.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(dead, open(os.path.join(BASE, "skipped_dead.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    out = "window.POSITIONS=" + json.dumps(all_positions, ensure_ascii=False, separators=(",", ":")) + ";"
    open(os.path.join(ROOT, "data.js"), "w", encoding="utf-8").write(out)

    print(f"\n完成：总职位 {len(all_positions)} 条 = 岗位表拆出 {len(positions)} + 公告级 {len(new_positions)}")
    print("城市分布：", dict(collections.Counter(p["city"] or "未标" for p in all_positions)))
    print("\n公告级职位样例：")
    for p in new_positions[:3]:
        print(" -", p["city"], "|", p["school"][:20], "|", p["job"][:40], "|", p["num"] or "人数详见原文")


if __name__ == "__main__":
    main()
