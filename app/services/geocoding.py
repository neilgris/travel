import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim 对真实地名（城市/城镇/村落/岛屿等）打分基本在 0.1 以上；
# 查不到中文地名时它会退化成模糊文本匹配，可能命中一个恰好同名的商铺/
# 餐厅（如「米科诺斯」误配到台北一家叫「米克諾斯」的餐厅），这类噪声
# 匹配的 importance 通常在 0.0001 量级，用阈值滤掉，宁可查不到也不要错。
MIN_IMPORTANCE = 0.05

def geocode(name):
    """用 OpenStreetMap Nominatim 查城市坐标和国家代码，失败返回 None。

    返回 (纬度, 经度, ISO 国家代码)；国家代码交给 flags.country_name_from_code
    转成中文名，避免依赖 Nominatim 自己的中文国名（繁简混杂、全称不统一）。
    """
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": name, "format": "json", "limit": 1, "addressdetails": 1},
            headers={"User-Agent": "travel-journal/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None
    if not data:
        return None
    result = data[0]
    if result.get("importance", 0) < MIN_IMPORTANCE:
        return None
    lat = float(result["lat"])
    lon = float(result["lon"])
    country_code = result.get("address", {}).get("country_code")
    return (lat, lon, country_code)
