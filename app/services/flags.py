"""国家名 → 国旗 emoji。

国旗是国家的纯函数，不入库：维护「中文名 → ISO alpha-2 代码」的小字典，
emoji 由代码两个字母映射到区域指示符（🇨🇳 等）动态生成。命中不了回退 🌍。
以后若给 geocoding 抓回 country_code，可直接走 flag_from_code 省掉字典。
"""

# 中文国家/地区名 → ISO 3166-1 alpha-2（含常见别名）
_NAME_TO_CODE = {
    "中国": "CN", "中国大陆": "CN", "香港": "HK", "澳门": "MO", "台湾": "TW",
    "日本": "JP", "韩国": "KR", "南韩": "KR", "朝鲜": "KP",
    "泰国": "TH", "越南": "VN", "新加坡": "SG", "马来西亚": "MY",
    "印度尼西亚": "ID", "印尼": "ID", "菲律宾": "PH", "柬埔寨": "KH",
    "老挝": "LA", "缅甸": "MM", "文莱": "BN",
    "印度": "IN", "尼泊尔": "NP", "斯里兰卡": "LK", "马尔代夫": "MV",
    "哈萨克斯坦": "KZ", "蒙古": "MN",
    "阿联酋": "AE", "阿拉伯联合酋长国": "AE", "卡塔尔": "QA",
    "沙特": "SA", "沙特阿拉伯": "SA", "以色列": "IL", "约旦": "JO",
    "伊朗": "IR", "土耳其": "TR",
    "美国": "US", "加拿大": "CA", "墨西哥": "MX", "古巴": "CU",
    "巴西": "BR", "阿根廷": "AR", "智利": "CL", "秘鲁": "PE",
    "英国": "GB", "爱尔兰": "IE", "法国": "FR", "德国": "DE",
    "意大利": "IT", "西班牙": "ES", "葡萄牙": "PT", "荷兰": "NL",
    "比利时": "BE", "瑞士": "CH", "奥地利": "AT", "希腊": "GR",
    "瑞典": "SE", "挪威": "NO", "芬兰": "FI", "丹麦": "DK",
    "冰岛": "IS", "俄罗斯": "RU", "波兰": "PL", "捷克": "CZ",
    "匈牙利": "HU", "克罗地亚": "HR", "梵蒂冈": "VA", "摩纳哥": "MC",
    "澳大利亚": "AU", "澳洲": "AU", "新西兰": "NZ", "斐济": "FJ",
    "埃及": "EG", "摩洛哥": "MA", "南非": "ZA", "肯尼亚": "KE",
    "坦桑尼亚": "TZ", "毛里求斯": "MU", "塞舌尔": "SC",
}


# 代码 → 中文名（_NAME_TO_CODE 的反查，同代码多个别名时取第一个/更常用的写法）
_CODE_TO_NAME = {}
for _name, _code in _NAME_TO_CODE.items():
    _CODE_TO_NAME.setdefault(_code, _name)


def country_name_from_code(code):
    """ISO alpha-2 代码 → 中文国家名；未收录返回 None。"""
    return _CODE_TO_NAME.get((code or "").strip().upper())


def flag_from_code(code):
    """ISO alpha-2 代码 → 国旗 emoji（两个字母各映射到区域指示符）。"""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def country_flag(name):
    """中文国家名 → 国旗 emoji；未收录（含 None / 「未分类」）回退 🌍。"""
    code = _NAME_TO_CODE.get((name or "").strip())
    return flag_from_code(code) if code else "🌍"
