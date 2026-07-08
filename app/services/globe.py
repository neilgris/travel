"""首页地球所需的展示数据：把所有旅程的 Leg 拍平成弧线 + 城市点。

只做取数与整形，不做地理编码（坐标缺失属数据问题）。见
docs/specs/2026-07-08-globe-home-design.md。
"""
from app.models.trip import Trip
from app.models.day import TRANSPORT_MODE_EMOJI

# 旅程配色板：按 start_date 升序循环取色，保证同一旅程颜色稳定。
TRIP_PALETTE = [
    "#e8792b", "#3d8bff", "#b06bff", "#2ecc9b", "#ff5d8f",
    "#f2c14e", "#5ce1e6", "#9b6bff", "#ff8a5c", "#4dd07b",
]


def _city_point(city):
    """城市有经纬度才算有效，否则返回 None。"""
    if city is None or city.latitude is None or city.longitude is None:
        return None
    return {"name": city.name, "lat": city.latitude, "lng": city.longitude}


def build_globe_data():
    """产出 home.html 所需的纯数据结构（见 spec 第 3 节 JSON schema）。"""
    trips = Trip.query.order_by(Trip.start_date, Trip.id).all()

    out_trips = []
    cities = {}          # name -> point，去重
    skipped = []         # 缺坐标/缺城市被跳过的段

    for i, trip in enumerate(trips):
        color = TRIP_PALETTE[i % len(TRIP_PALETTE)]
        arcs, modes = [], []
        for leg in trip.legs:
            frm = _city_point(leg.from_city)
            to = _city_point(leg.to_city)
            if frm is None or to is None:
                skipped.append({
                    "trip": trip.title,
                    "from": leg.from_city.name if leg.from_city else None,
                    "to": leg.to_city.name if leg.to_city else None,
                })
                continue
            mode = leg.transport_mode
            arcs.append({
                "from": frm,
                "to": to,
                "mode": mode,
                "emoji": TRANSPORT_MODE_EMOJI.get(mode, ""),
            })
            if mode and mode not in modes:
                modes.append(mode)
            cities[frm["name"]] = frm
            cities[to["name"]] = to

        out_trips.append({
            "id": trip.id,
            "title": trip.title,
            "start_date": trip.start_date.isoformat() if trip.start_date else None,
            "end_date": trip.end_date.isoformat() if trip.end_date else None,
            "color": color,
            "url": f"/trips/{trip.id}",
            "modes": modes,
            "arcs": arcs,
        })

    return {
        "trips": out_trips,
        "cities": list(cities.values()),
        "skipped": {"count": len(skipped), "legs": skipped},
    }
