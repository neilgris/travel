"""旅程故事页所需的展示数据：按天的内容 + 小地图数据。

只做取数与整形，金额换算复用 services.stats.to_cny。见
docs/specs/2026-07-14-trip-story-page-design.md。
"""
from decimal import Decimal

from app.services.stats import to_cny


def _image_subpath(path):
    """DayImage.path 形如 'uploads/trips/4/x.jpg'，去掉 uploads/ 前缀供 main.uploads 用。"""
    return path.split("uploads/", 1)[-1] if "uploads/" in path else path


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


def story_data(trip):
    rate_map = {c.currency_code: Decimal(c.rate) for c in trip.currencies}
    days = [_day_content(d, rate_map)
            for d in sorted(trip.days, key=lambda d: d.date)]
    return {"days": days, "map": {}}
