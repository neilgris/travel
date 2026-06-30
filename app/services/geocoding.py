import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def geocode(name):
    """用 OpenStreetMap Nominatim 查城市坐标，失败返回 None。"""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": name, "format": "json", "limit": 1},
            headers={"User-Agent": "travel-journal/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None
    if not data:
        return None
    return (float(data[0]["lat"]), float(data[0]["lon"]))
