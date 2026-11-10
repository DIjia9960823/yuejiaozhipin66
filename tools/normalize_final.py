# -*- coding: utf-8 -*-
"""管线最后一步：
  1. edu/stage/establishment 归一化 + 详见原文→未标明
  2. 同校同职位同公告的去重
  3. 校名→城市映射补齐未标明城市
  4. 按万行教师网广东频道城市顺序排序（21 市）
让前端筛选器干净、语义一致。"""
import json, re, os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(ROOT, "data.js")

# 万行教师网（job910）广东地区频道城市顺序，共 21 市
GD_CITIES = [
    "广州", "韶关", "深圳", "珠海", "汕头", "佛山", "江门", "湛江",
    "茂名", "肇庆", "惠州", "梅州", "汕尾", "河源", "阳江", "清远",
    "东莞", "中山", "潮州", "揭阳", "云浮",
]

# 校名→城市映射（补 crawler 没解析到 city 的高校/职校）
SCHOOL_TO_CITY = {
    "广东石油化工学院": "茂名",
    "韩山师范学院": "潮州",
    "广东科学技术职业学院": "珠海",
    "广东交通职业技术学院": "广州",
    "广东司法警官职业学院": "广州",
    "广东体育职业技术学院": "广州",
    "广东文艺职业学院": "广州",
    "广东行政职业学院": "广州",
    "广东邮电职业技术学院": "广州",
    "广东工贸职业技术学院": "广州",
    "广东机电职业技术学院": "广州",
    "广东建设职业技术学院": "广州",
    "广东水利电力职业技术学院": "广州",
    "广东环境保护工程职业学院": "佛山",
    "广东职业技术学院": "佛山",
    "广东女子职业技术学院": "广州",
    "广东轻工职业技术学院": "广州",
    "广东理工职业学院": "广州",
    "广东工程职业技术学院": "广州",
    "广东农工商职业技术学院": "广州",
    "广东技术师范大学": "广州",
    "广东第二师范学院": "广州",
    "广东财经大学": "广州",
    "广东工业大学": "广州",
    "广东外语外贸大学": "广州",
    "广东中医药大学": "广州",
    "广东医科大学": "湛江",
    "广东海洋大学": "湛江",
    "广东文理职业学院": "湛江",
    "广东酒店管理职业技术学院": "东莞",
    "广东创新科技职业学院": "东莞",
    "广东科技学院": "东莞",
    "广东亚视演艺职业学院": "东莞",
    "广东岭南职业技术学院": "广州",
    "广东城市职业学院": "广州",
    "广东南华工商职业学院": "广州",
    "广东青年职业学院": "广州",
    "广东科贸职业学院": "广州",
    "广东生物工程职业技术学院": "广州",
    "广东生态工程职业学院": "广州",
    "广东舞蹈戏剧职业学院": "广州",
    "广东警官学院": "广州",
    "仲恺农业工程学院": "广州",
    "星海音乐学院": "广州",
    "广州美术学院": "广州",
    "广州体育学院": "广州",
    "广东药科大学": "广州",
    "广州铁路职业技术学院": "广州",
    "广州民航职业技术学院": "广州",
    "深圳职业技术学院": "深圳",
    "深圳信息职业技术学院": "深圳",
    "深圳大学": "深圳",
    "南方科技大学": "深圳",
    "深圳技术大学": "深圳",
    "深圳北理莫斯科大学": "深圳",
    "香港中文大学（深圳）": "深圳",
    "汕头大学": "汕头",
    "汕头职业技术学院": "汕头",
    "韶关学院": "韶关",
    "肇庆学院": "肇庆",
    "肇庆医学高等专科学校": "肇庆",
    "惠州学院": "惠州",
    "河源职业技术学院": "河源",
    "阳江职业技术学院": "阳江",
    "清远职业技术学院": "清远",
    "东莞职业技术学院": "东莞",
    "东莞理工学院": "东莞",
    "中山职业技术学院": "中山",
    "中山火炬职业技术学院": "中山",
    "佛山大学": "佛山",
    "佛山职业技术学院": "佛山",
    "顺德职业技术学院": "佛山",
    "五邑大学": "江门",
    "江门职业技术学院": "江门",
    "茂名职业技术学院": "茂名",
    "茂名幼儿师范专科学校": "茂名",
    "汕尾职业技术学院": "汕尾",
    "潮州卫生健康职业学院": "潮州",
    "揭阳职业技术学院": "揭阳",
    "云浮职业技术学院": "云浮",
}


def norm_edu(v):
    if not v: return "未标明"
    v = v.strip()
    if v in ("学历要求", "学历 要求", "学历",
             "申报专任教师任教专业（教研室）情况",
             "社会人员需具备初级及以上职称或相关从教/从业经历1年及以上（详见报考职位其他条件）"):
        return "未标明"
    if v == "详见原文": return "未标明"
    if "博士" in v: return "博士"
    if re.search(r"硕|研究生", v): return "硕士"
    if "大专" in v: return "大专"
    if "本科" in v: return "本科"
    return "未标明"


def norm_stage(v):
    if not v: return "未标明"
    if v in ("高中", "初中", "中小学", "中学"): return "中学"
    return v


def norm_other(v):
    if v == "详见原文": return "未标明"
    return v


def dedupe(pos):
    groups = defaultdict(list)
    for p in pos:
        key = (p.get("school", ""), p.get("job", ""), p.get("annTitle", ""))
        groups[key].append(p)
    merged = []
    for key, items in groups.items():
        if len(items) == 1:
            merged.append(items[0]); continue
        m = dict(items[0])
        nums = []
        for it in items:
            try:
                n = int(re.sub(r"\D", "", it.get("num", "0")) or "0")
                if n > 0: nums.append(n)
            except Exception: pass
        if nums: m["num"] = str(sum(nums))
        dls = [it.get("deadline", "") for it in items if it.get("deadline")]
        if dls: m["deadline"] = min(dls)
        merged.append(m)
    return merged


def fix_city_by_school(pos):
    changed = 0
    for p in pos:
        if not p.get("city") or p.get("city") in ("", "未标明"):
            school = p.get("school", "")
            if school in SCHOOL_TO_CITY:
                p["city"] = SCHOOL_TO_CITY[school]; changed += 1
            else:
                for city in GD_CITIES:
                    if city in school:
                        p["city"] = city; changed += 1; break
    print(f"🏫 按校名补了 {changed} 条城市")
    return pos


def sort_by_plate_order(pos):
    def sort_key(p):
        c = p.get("city", "")
        if c in GD_CITIES:
            return (0, GD_CITIES.index(c))
        return (1, 9999)
    pos.sort(key=sort_key)
    return pos


def main():
    print(f"📖 读 {DATA_JS}")
    s = open(DATA_JS, encoding="utf-8").read()
    pos, _ = json.JSONDecoder().raw_decode(s[s.index("["):])
    before = len(pos)

    # 1. 字段归一化
    for p in pos:
        p["edu"] = norm_edu(p.get("edu", ""))
        p["stage"] = norm_stage(p.get("stage", ""))
        p["establishment"] = norm_other(p.get("establishment", ""))

    # 2. 去重
    pos = dedupe(pos)

    # 3. 校名→城市补齐
    pos = fix_city_by_school(pos)

    # 4. 按万行顺序排序
    pos = sort_by_plate_order(pos)

    out = "window.POSITIONS=" + json.dumps(pos, ensure_ascii=False, separators=(",", ":")) + ";"
    open(DATA_JS, "w", encoding="utf-8").write(out)

    print(f"\n✅ 归一化完成: {before} → {len(pos)} 条（去重 {before - len(pos)}）")
    print(f"\n📊 万行顺序城市分布：")
    c = Counter(p.get("city", "未标明") for p in pos)
    for city in GD_CITIES:
        n = c.get(city, 0)
        mark = "✅" if n > 0 else "❌"
        print(f"  {mark} {city}: {n}")
    print(f"  未标: {c.get('未标明', 0)}")
    print(f"\n字段分布：")
    for label, field in [("学历", "edu"), ("学段", "stage"), ("编制", "establishment")]:
        print(f"  {label}: " + ", ".join(f"{n}×{v}" for v, n in Counter(p[field] for p in pos).most_common()))


if __name__ == "__main__":
    main()
