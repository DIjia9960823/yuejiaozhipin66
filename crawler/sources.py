# -*- coding: utf-8 -*-
"""
数据源配置：想增加 / 删除城市或学校，只改这个文件即可。

home    = 该单位官网首页（爬虫会自动从首页找到「通知公告 / 招聘公告」栏目）
city    = 城市名（会显示在网站上）；高校统一写 "高校"
name    = 数据来源名称（会显示在网站上）
entries = 可选，手工补充栏目页地址（自动发现没找到时用）
enabled = 改成 False 可临时停用某个源
"""

SOURCES = [
    # =================== 地级市教育局 ===================
    {
        "city": "广州",
        "name": "广州市教育局",
        "home": "https://jyj.gz.gov.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "深圳",
        "name": "深圳市教育局",
        "home": "https://szeb.sz.gov.cn/",
        "entries": [
            "https://szeb.sz.gov.cn/home/xxgk/flzy/rsxx2/ryzp/index.html",
        ],
        # 深圳的网站是JS动态加载，真实数据在这个JSON接口里
        "json_columns": ["https://szeb.sz.gov.cn/postmeta/i/61955.json"],
        "enabled": True,
    },
    {
        "city": "珠海",
        "name": "珠海市教育局",
        "home": "https://zhjy.zhuhai.gov.cn/",
        "entries": [
            "https://zhjy.zhuhai.gov.cn/ywgz/jsdw/index.html",
            "https://zhjy.zhuhai.gov.cn/zwgk/gsgg/index.html",
        ],
        "enabled": True,
    },
    {
        "city": "汕头",
        "name": "汕头市教育局",
        "home": "https://www.shantou.gov.cn/edu/",
        "entries": [
            "https://www.shantou.gov.cn/edu/ymys/tzgg/index.html",
        ],
        # 政府信息公开平台：人事信息 3624 / 通知公告 3608
        "gkmlpt": [
            ("https://www.shantou.gov.cn/stsjyj/gkmlpt", "3624"),
            ("https://www.shantou.gov.cn/stsjyj/gkmlpt", "3608"),
        ],
        "enabled": True,
    },
    {
        "city": "佛山",
        "name": "佛山市教育局",
        "home": "https://edu.foshan.gov.cn/",
        "entries": [
            "https://edu.foshan.gov.cn/gg/zhaopinxinxi/index.html",
            "https://edu.foshan.gov.cn/zwgk/rcjl/index.html",
        ],
        "enabled": True,
    },
    {
        "city": "韶关",
        "name": "韶关市教育局",
        "home": "http://jy.sg.gov.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "湛江",
        "name": "湛江市教育局",
        "home": "https://www.zhanjiang.gov.cn/zhjedu/",
        "entries": ["https://www.zhanjiang.gov.cn/zjsfw/bmdh/jyj/zwgk/tzgg/index.html"],
        "enabled": True,
    },
    {
        "city": "肇庆",
        "name": "肇庆市教育局",
        "home": "https://www.zhaoqing.gov.cn/zqjyj/",
        "entries": [],
        # 政府信息公开平台：人事信息 15 / 公告公示 20942
        "gkmlpt": [
            ("https://www.zhaoqing.gov.cn/zqjyj/gkmlpt", "15"),
            ("https://www.zhaoqing.gov.cn/zqjyj/gkmlpt", "20942"),
        ],
        "enabled": True,
    },
    {
        "city": "江门",
        "name": "江门市教育局",
        "home": "https://www.jiangmen.gov.cn/bmpd/jmsjyj/",
        "entries": ["https://www.jiangmen.gov.cn/bmpd/jmsjyj/zwgk/tzgg/index.html"],
        "enabled": True,
    },
    {
        "city": "茂名",
        "name": "茂名市教育局",
        "home": "http://mmjyj.maoming.gov.cn/",
        "entries": ["http://mmjyj.maoming.gov.cn/gkmlpt/mindex"],
        "enabled": True,
    },
    {
        "city": "惠州",
        "name": "惠州市教育局",
        "home": "https://jyj.huizhou.gov.cn/",
        "entries": [],
        # 政府信息公开平台：通知公告 404
        "gkmlpt": [
            ("http://jyj.huizhou.gov.cn/gkmlpt", "404"),
        ],
        "enabled": True,
    },
    {
        "city": "梅州",
        "name": "梅州市教育局",
        # 注意：官网 2026-11 起返回 HTTP 521（源站不可用），暂时停用，恢复后改成 enabled=True
        "home": "https://www.meizhou.gov.cn/zwgk/zfjg/mzjy/",
        "entries": [],
        "enabled": False,
    },
    {
        "city": "汕尾",
        "name": "汕尾市教育局",
        "home": "https://www.shanwei.gov.cn/swjyj/",
        "entries": [],
        # 政府信息公开平台：人事信息 1066
        "gkmlpt": [
            ("https://www.shanwei.gov.cn/swsjyj/gkmlpt", "1066"),
        ],
        "enabled": True,
    },
    {
        "city": "河源",
        "name": "河源市教育局",
        "home": "http://www.heyuan.gov.cn/bmjy/hysjyj/",
        "entries": [],
        # 首页是 JS 跳转，真实列表在 JSON 接口里（通知公告 2646）
        "json_columns": ["http://www.heyuan.gov.cn/postmeta/i/2646.json"],
        "enabled": True,
    },
    {
        "city": "阳江",
        "name": "阳江市教育局",
        # 原 /yjjyj/ 被防火墙拦截（403），改走政府信息公开平台 gkmlpt（已验证可通）
        "home": "https://www.yangjiang.gov.cn/gkmlpt/mindex",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "清远",
        "name": "清远市教育局",
        # 注意：整站 WAF 拦截（GET 412 / 405），暂无可用入口
        "home": "http://www.gdqy.gov.cn/channel/qysjyj/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "东莞",
        "name": "东莞市教育局",
        "home": "https://edu.dg.gov.cn/",
        "entries": [
            "https://edu.dg.gov.cn/flfw/jsgl/mindex.html",
            "https://edu.dg.gov.cn/flfw/jsgl/rsxx/index.html",
            "https://edu.dg.gov.cn/jyzx/gsgg/",
        ],
        "enabled": True,
    },
    {
        "city": "中山",
        "name": "中山市教育和体育局",
        "home": "https://jtj.zs.gov.cn/",
        "entries": [
            "https://jtj.zs.gov.cn/zwgk/tzgg/",
            "https://jtj.zs.gov.cn/gkmlpt/mindex",
        ],
        "enabled": True,
    },
    {
        "city": "潮州",
        "name": "潮州市教育局",
        # 原来 /czjyj/ 被防火墙拦截（403），改用市府网站里的教育局栏目
        "home": "https://www.chaozhou.gov.cn/zwgk/szfgz/sjyj/index.html",
        "entries": [
            "https://www.chaozhou.gov.cn/zwgk/szfgz/sjyj/tzgg/index.html",
        ],
        "enabled": True,
    },
    {
        "city": "揭阳",
        "name": "揭阳市教育局",
        "home": "http://www.jieyang.gov.cn/jyj/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "云浮",
        "name": "云浮市教育局",
        "home": "https://www.yunfu.gov.cn/jyj/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "广东",
        "name": "广东省教育厅",
        "home": "https://edu.gd.gov.cn/",
        "entries": ["https://edu.gd.gov.cn/zwgknew/gsgg/index.html"],
        "enabled": True,
    },
    {
        "city": "广东",
        "name": "广东省人社厅",
        "home": "https://hrss.gd.gov.cn/",
        "entries": ["https://hrss.gd.gov.cn/zwgk/sydwzp/zpgg/index.html"],
        "enabled": True,
    },

    # =================== 高校（教师招聘大头） ===================
    {
        "city": "高校",
        "name": "中山大学",
        "home": "https://rcb.sysu.edu.cn/",
        "entries": ["https://rcb.sysu.edu.cn/zp"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "华南理工大学",
        "home": "https://www2.scut.edu.cn/hr/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "华南师范大学",
        "home": "http://rsc.scnu.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广东工业大学",
        "home": "https://hr.gdut.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "深圳大学",
        "home": "https://hr.szu.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "暨南大学",
        "home": "https://hrdam.jnu.edu.cn/",
        "entries": ["https://hrdam.jnu.edu.cn/264/list.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "华南农业大学",
        "home": "https://hr.scau.edu.cn/",
        "entries": ["https://hr.scau.edu.cn/zpgg/list.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广州大学",
        "home": "https://rsc.gzhu.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广东外语外贸大学",
        "home": "https://rsc.gdufs.edu.cn/",
        "entries": ["https://rsc.gdufs.edu.cn/zpxx/zpdt.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广东财经大学",
        "home": "https://rsc.gdufe.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "南方医科大学",
        "home": "https://portal.smu.edu.cn/renshi/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广州医科大学",
        "home": "http://rsc.gzhmu.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广州中医药大学",
        "home": "https://rsc.gzucm.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "南方科技大学",
        "home": "https://talent.sustech.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "汕头大学",
        "home": "https://rsc.stu.edu.cn/",
        "entries": [],
        "enabled": True,
    },

    {
        "city": "高校",
        "name": "广东海洋大学",
        "home": "https://rsc.gdou.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广东医科大学",
        "home": "https://rsc.gdmu.edu.cn/",
        "entries": ["https://rsc.gdmu.edu.cn/rczp1/zpgg.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广东技术师范大学",
        "home": "https://rsc.gpnu.edu.cn/",
        "entries": ["https://rsc.gpnu.edu.cn/rczp.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广东第二师范学院",
        "home": "https://www.gdei.edu.cn/",
        "entries": ["https://www.gdei.edu.cn/rsc/zpgg/list.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广东金融学院",
        "home": "https://rsc.gduf.edu.cn/",
        "entries": ["https://rsc.gduf.edu.cn/xwgg.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "星海音乐学院",
        "home": "https://rsc.xhcom.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "肇庆学院",
        "home": "https://rsc.zqu.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "惠州学院",
        "home": "https://rsc.hzu.edu.cn/",
        "entries": ["https://rsc.hzu.edu.cn/180/list.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "韶关学院",
        "home": "https://rsc.sgu.edu.cn/",
        "entries": ["http://www.sgu.edu.cn/rczpw/zpgg.htm?FM_SYS_ID=sgxy"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "岭南师范学院",
        "home": "https://d.lingnan.edu.cn/rsc/",
        "entries": ["https://d.lingnan.edu.cn/rsc/rczp.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "五邑大学",
        "home": "https://www.wyu.edu.cn/hr/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "东莞理工学院",
        "home": "https://rs.dgut.edu.cn/",
        "entries": [],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "顺德职业技术大学",
        "home": "https://rsc.sdpt.edu.cn/",
        "entries": ["https://rsc.sdpt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1203"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "深圳技术大学",
        "home": "https://hr.sztu.edu.cn/",
        "entries": ["https://hr.sztu.edu.cn/zpqs.htm"],
        "enabled": True,
    },
    {
        "city": "高校",
        "name": "广东交通职业技术学院",
        "home": "https://rsc.gdcp.edu.cn/",
        "entries": [],
        "enabled": True,
    },

    # =================== 民办高校（名称后面带「民办」方便区分） ===================
    {
        "city": "东莞",
        "name": "广东科技学院（民办）",
        "home": "https://www.gdust.edu.cn/",
        "entries": ["https://www.gdust.edu.cn/rsc/rcyj/rcyj"],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "广州华商学院（民办）",
        "home": "https://www.gzhs.edu.cn/",
        "entries": ["https://www.gzhs.edu.cn/rcyj.htm"],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "广州软件学院（民办）",
        "home": "https://www.gzus.edu.cn/",
        "entries": ["https://www.gzus.edu.cn/rczp.htm"],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "广州应用科技学院（民办）",
        "home": "http://www.gzasc.edu.cn/",
        "entries": ["http://www.gzasc.edu.cn/rsc/rczp.htm"],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "广州理工学院（民办）",
        "home": "https://www.gzist.edu.cn/",
        "entries": ["https://www.gzist.edu.cn/rcyj/zpqs.htm"],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "广州工商学院（民办）",
        "home": "http://www.gzgs.edu.cn/",
        "entries": ["http://www.gzgs.edu.cn/rsc/rczp.htm"],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "广外南国商学院（民办）",
        "home": "https://www.gwng.edu.cn/",
        "entries": ["https://www.gwng.edu.cn/rsc/992/list.htm"],
        "enabled": True,
    },
    {
        "city": "湛江",
        "name": "广东文理职业学院（民办）",
        "home": "https://www.gdwlxy.edu.cn/",
        "entries": ["https://www.gdwlxy.edu.cn/Html/Article/list_578.html"],
        "enabled": True,
    },
    {
        "city": "肇庆",
        "name": "广东理工学院（民办）",
        "home": "https://www.gdlgxy.edu.cn/",
        "entries": ["https://rsc.gdlgxy.edu.cn/rczp/zpgg.htm"],
        "enabled": True,
    },
    {
        "city": "东莞",
        "name": "广东创新科技职业学院（民办）",
        "home": "http://www.gdcxxy.edu.cn/",
        "entries": ["http://www.gdcxxy.edu.cn/rczp/"],
        "enabled": True,
    },

    # ===== 区县教育局（广州，gkmlpt 栏目 id 由 probe_district_sources 系列探测得到）=====
    {
        "city": "广州",
        "name": "海珠区教育局",
        "home": "http://www.haizhu.gov.cn/gzhzjy/gkmlpt/index",
        "entries": [],
        "gkmlpt": [("http://www.haizhu.gov.cn/gzhzjy/gkmlpt", "15600")],  # 教师管理
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "番禺区教育局",
        "home": "http://www.panyu.gov.cn/gzpyjy/gkmlpt/index",
        "entries": [],
        "gkmlpt": [("http://www.panyu.gov.cn/gzpyjy/gkmlpt", "1336")],  # 通知公告
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "花都区教育局",
        "home": "http://www.huadu.gov.cn/gzhdjy/gkmlpt/index",
        "entries": [],
        "gkmlpt": [("http://www.huadu.gov.cn/gzhdjy/gkmlpt", "15822")],  # 教师管理
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "荔湾区教育局",
        "home": "http://www.lw.gov.cn/gzlwjy/gkmlpt/index",
        "entries": [],
        "gkmlpt": [
            ("http://www.lw.gov.cn/gzlwjy/gkmlpt", "13018"),  # 部门文件
            ("http://www.lw.gov.cn/gzlwjy/gkmlpt", "13026"),  # 其他
        ],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "白云区教育局",
        "home": "http://www.by.gov.cn/gzbyjy/gkmlpt/index",
        "entries": [],
        "gkmlpt": [
            ("http://www.by.gov.cn/gzbyjy/gkmlpt", "8296"),  # 其他
            ("http://www.by.gov.cn/gzbyjy/gkmlpt", "8298"),  # 其他
        ],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "南沙区教育局",
        "home": "http://www.gzns.gov.cn/gznsjy/gkmlpt/index",
        "entries": [],
        "gkmlpt": [
            ("http://www.gzns.gov.cn/gznsjy/gkmlpt", "10348"),  # 政府文件
            ("http://www.gzns.gov.cn/gznsjy/gkmlpt", "10353"),  # 其他
        ],
        "enabled": True,
    },
    {
        "city": "广州",
        "name": "天河区教育局",
        "home": "http://www.thnet.gov.cn/gzjg/qzf/qjyj/index.html",
        "entries": ["http://www.thnet.gov.cn/gzjg/qzf/qjyj/tzgg/index.html"],
        "enabled": True,
    },
    # 越秀/黄埔/从化/增城区教育局：gkmlpt 与局网站均未找到招聘栏目（2026-11 探测），
    # 深圳各区网站用国密证书、Python 无法抓取，均暂缓。

    # ===== 以后要加学校，复制一段改三个字段即可（city 写 "高校"） =====
]

# 每个数据源最多抓多少个栏目页 / 多少个候选文章
MAX_COLUMNS = 4
MAX_ARTICLES_PER_SOURCE = 40
MAX_PAGES_PER_COLUMN = 2

# 判断一条公告是不是「教师招聘」类
KEYWORD_MUST = ["招聘", "招考", "招录", "选调", "选聘", "引进", "诚聘", "公开招聘"]
KEYWORD_TEACHER = [
    "教师", "教职工", "教职员", "教研员", "校长", "学校", "学科",
    "大学", "学院", "中学", "小学", "幼儿园", "教育",
]
KEYWORD_EXCLUDE = [
    "招标", "中标", "成交", "采购", "遴选结果", "承办", "培训机构",
    "资格考试", "资格认定", "评审结果", "拟聘", "聘用人员公示",
    "成绩", "笔试", "面试", "体检", "考察", "获奖", "名单", "递补",
    "拟录用", "拟选调", "人员公示", "公务员", "招生入学", "研学",
    "医院", "卫生", "医疗",
]

# 没有写截止日期的公告，默认发布后多少天失效
RECENT_DAYS = 180

# 民办学校同样用 180 天
PRIVATE_RECENT_DAYS = 180
