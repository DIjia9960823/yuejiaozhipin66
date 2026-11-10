# -*- coding: utf-8 -*-
"""官方来源判定 —— 全站唯一闸门。

规矩（用户定的，不许改）：
  第三方（公考雷达、万行教师网、中公、事业单位招聘网等）只能当"发现渠道"。
  入库的 sourceUrl 和 content 必须是官方原文。
  找不到官方原文的，宁可丢掉，也不许拿第三方链接顶上。
"""
import os
from urllib.parse import urlparse

# 已知第三方聚合/转载站：出现在这些域名上一律不许入库
THIRD_PARTY_DOMAINS = (
    "job910.com",        # 万行教师网
    "gongkaoleida.com",  # 公考雷达
    "offcn.com",         # 中公教育
    "qgsydw.com",        # 全国事业单位招聘网
    "huatu.com",         # 华图
    "eol.cn",            # 中国教育在线
    "51test.net",        # 无忧考网
    "gaoxiaojob.com",    # 高校人才网
    "yingjiesheng.com",  # 应届生求职网
    "zhihu.com",
    "sohu.com",
    "163.com",
    "qq.com",
    "sina.com.cn",
    "baidu.com",
    "toutiao.com",
)

# 官方域名后缀
OFFICIAL_SUFFIXES = (".gov.cn", ".edu.cn")


def host_of(url):
    try:
        h = urlparse(url or "").netloc.lower()
        return h.split(":")[0]          # 去掉端口
    except Exception:
        return ""


def is_official(url, source=""):
    """这条能不能入库。False = 第三方，必须丢掉。"""
    h = host_of(url)
    if not h:
        return False                     # 没有链接，没法核验，不收
    if "转载" in (source or ""):
        return False
    for d in THIRD_PARTY_DOMAINS:
        if h == d or h.endswith("." + d):
            return False
    return True
