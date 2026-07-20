"""旅程故事页所需的展示数据：按天的内容 + 小地图数据。

只做取数与整形，金额换算复用 services.stats.to_cny。见
docs/specs/2026-07-14-trip-story-page-design.md。
"""
from decimal import Decimal

from app.services.distance import has_coords
from app.services.stats import to_cny


def _image_subpath(path):
    """DayImage.path 形如 'uploads/trips/4/x.jpg'，去掉 uploads/ 前缀供 main.uploads 用。"""
    return path.split("uploads/", 1)[-1] if "uploads/" in path else path


def point(city):
    """城市有经纬度才算有效，否则 None。"""
    if not has_coords(city):
        return None
    return {"lat": city.latitude, "lng": city.longitude, "name": city.name}


def _day_content(day, rate_map):
    spend = Decimal("0.00")
    entries = []
    for e in day.entries:
        cny = to_cny(e.amount, e.currency_code, rate_map)
        spend += cny
        entries.append({"category": e.category, "title": e.title, "cny": cny})
    entries.sort(key=lambda x: x["cny"], reverse=True)
    return {
        "date": day.date,
        "city_name": day.city.name if day.city else None,
        "journal": day.diary or None,
        "images": [_image_subpath(img.path) for img in day.images],
        "spend_cny": spend,
        "highlights": entries[:3],
    }


def _map_data(trip, sorted_days):
    route, cities, seen = [], [], set()
    # 每城的停留天数：供前端地图取景优先聚焦「住过的城市」，让转机/出发地不撑大画框。
    day_counts = {}
    for d in sorted_days:
        if d.city and d.city.name:
            day_counts[d.city.name] = day_counts.get(d.city.name, 0) + 1

    def _city(p):
        # 城市点副本 + 天数（副本避免与 route 端点共享同一 dict）。
        return {**p, "days": day_counts.get(p["name"], 0)}

    for leg in trip.legs:  # Trip.legs 已按 seq 排序
        frm, to = point(leg.from_city), point(leg.to_city)
        if frm is None or to is None:
            continue
        route.append({"from": frm, "to": to})
        for p in (frm, to):
            if p["name"] not in seen:
                seen.add(p["name"])
                cities.append(_city(p))
    day_cities = []
    for d in sorted_days:
        p = point(d.city)
        # 各天城市也画成点（含无 Leg 的旅程、以及不在任何 Leg 端点上的天），按名去重。
        if p and p["name"] not in seen:
            seen.add(p["name"])
            cities.append(_city(p))
        day_cities.append({"lat": p["lat"], "lng": p["lng"]} if p else None)
    return {"route": route, "cities": cities, "day_cities": day_cities}


def story_data(trip):
    rate_map = {c.currency_code: Decimal(c.rate) for c in trip.currencies}
    sorted_days = sorted(trip.days, key=lambda d: d.date)
    days = [_day_content(d, rate_map) for d in sorted_days]
    return {"days": days, "map": _map_data(trip, sorted_days)}
