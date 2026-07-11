import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

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
    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    country_code = data[0].get("address", {}).get("country_code")
    return (lat, lon, country_code)
