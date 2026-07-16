"""人生足迹总览与年度报告的聚合层。

两个页面（/insights/ 与 /insights/<year>）共用这一层，口径只在这里定义一次：

- 年份归属：整趟按 start_date 的年份，不按天拆分。库里仅 1 趟跨年旅程
  （201612 - 台北，2016-12-29 → 2017-01-02），按天拆会让同一趟同时出现在
  两年的报告里，叙事别扭且旅程数与总览页对不上，为 2 天不值得。见 DECISIONS D21。
- 在途天数：(end_date - start_date + 1) 求和，重叠日期去重（当前数据无重叠，防御性）。
- 新解锁国家：该国家首次到访旅程的 start_date 年份。
- 国家计数：City.country 字段值原样计数，同 stats.trips_overview 既有口径。

金额换算复用 services.stats，里程复用 services.distance，均不重写。
设计见 docs/specs/2026-07-17-insights-design.md。
"""
import datetime as dt
from decimal import Decimal

from app.models.city import City
from app.models.day import CATEGORIES
from app.services.distance import haversine_km, trip_distance_km
from app.services.stats import to_cny, trip_stats, trips_overview
# _point 复用故事页的城市点整形（有经纬度才算有效），避免两处各写一遍。
from app.services.story import _point

# 住处：most_visited_city 的排除项、farthest_city 的距离基准。
# 与 stats.trips_overview 里 top_cities 排除北京的口径一致。
HOME_CITY = "北京"
CHINA = "中国"


def _sorted(trips):
    """按开始日期升序，同日期按 id 兜底（同 blueprints/trips.py 的相邻旅程口径）。"""
    return sorted(trips, key=lambda t: (t.start_date, t.id))


def _trip_dates(trip):
    """一趟旅程覆盖的日期集合，含首尾。"""
    n = (trip.end_date - trip.start_date).days
    return {trip.start_date + dt.timedelta(days=i) for i in range(n + 1)}


def _days_on_road(trips):
    """在途天数：各旅程日期跨度并集的大小（重叠日期只算一天）。"""
    days = set()
    for t in trips:
        days |= _trip_dates(t)
    return len(days)


def _trip_countries(trip):
    """一趟旅程涉及的国家集合（Trip.cities 由 Leg 推导，见 models/trip.py）。"""
    return {c.country for c in trip.cities if c.country}


def _first_abroad(trips):
    """最早一趟含非中国城市的旅程。"""
    for t in _sorted(trips):
        abroad = sorted(c for c in _trip_countries(t) if c != CHINA)
        if abroad:
            return {"trip_id": t.id, "title": t.title,
                    "date": t.start_date, "countries": abroad}
    return None


def _farthest_trip(trips):
    """里程最长的旅程。全程无坐标（里程 0）的旅程不参与。"""
    best = None
    for t in _sorted(trips):
        km = trip_distance_km(t)
        if km <= 0:
            continue
        if best is None or km > best["distance_km"]:
            best = {"trip_id": t.id, "title": t.title,
                    "date": t.start_date, "distance_km": km}
    return best


def _longest_trip(trips):
    """在途天数最多的旅程。"""
    best = None
    for t in _sorted(trips):
        days = (t.end_date - t.start_date).days + 1
        if best is None or days > best["days"]:
            best = {"trip_id": t.id, "title": t.title,
                    "date": t.start_date, "days": days}
    return best


def _most_visited_city(trips):
    """覆盖旅程数最多的城市（排除住处），带首末次到访日期。

    并列时按城市名升序取第一个，与 trips_overview 的 top_cities 排序口径一致。
    """
    visits = {}
    for t in _sorted(trips):
        for name in sorted({c.name for c in t.cities if c.name != HOME_CITY}):
            visits.setdefault(name, []).append(t.start_date)
    if not visits:
        return None
    name = min(visits, key=lambda n: (-len(visits[n]), n))
    dates = visits[name]   # _sorted 保证已按日期升序
    return {"city": name, "count": len(dates),
            "first_date": dates[0], "last_date": dates[-1]}


def _farthest_city(trips):
    """距住处直线距离最大的城市。住处不在库里或无坐标时无基准，返回 None。"""
    home = City.query.filter_by(name=HOME_CITY).first()
    if home is None or home.latitude is None or home.longitude is None:
        return None
    best = None
    seen = set()
    for t in trips:
        for c in t.cities:
            if c.id in seen or c.latitude is None or c.name == HOME_CITY:
                continue
            seen.add(c.id)
            km = round(haversine_km(home.latitude, home.longitude,
                                    c.latitude, c.longitude))
            if best is None or km > best["distance_km"]:
                best = {"city": c.name, "country": c.country, "distance_km": km}
    return best


def _milestones(trips):
    return {
        "first_abroad": _first_abroad(trips),
        "farthest_trip": _farthest_trip(trips),
        "longest_trip": _longest_trip(trips),
        "most_visited_city": _most_visited_city(trips),
        "farthest_city": _farthest_city(trips),
    }


def _first_year_by_country(trips):
    """{国家: 首次到访年份}——按旅程 start_date 的年份归属。"""
    first = {}
    for t in _sorted(trips):
        for country in _trip_countries(t):
            first.setdefault(country, t.start_date.year)
    return first


def _year_rows(trips):
    """逐年聚合，年份连续（空档年补零）。空档年本身是信息（如疫情停摆）。"""
    by_year = {}
    for t in trips:
        by_year.setdefault(t.start_date.year, []).append(t)
    if not by_year:
        return []

    new_by_year = {}
    for country, year in _first_year_by_country(trips).items():
        new_by_year.setdefault(year, []).append(country)

    rows = []
    for year in range(min(by_year), max(by_year) + 1):
        year_trips = by_year.get(year, [])
        total = sum((trip_stats(t)["total_cny"] for t in year_trips), Decimal("0.00"))
        rows.append({
            "year": year,
            "trip_count": len(year_trips),
            "total_cny": total,
            "distance_km": sum(trip_distance_km(t) for t in year_trips),
            "days_on_road": _days_on_road(year_trips),
            "new_countries": sorted(new_by_year.get(year, [])),
        })
    return rows


def _busiest_year(rows):
    """旅程数最多的年份；并列取最早那年。"""
    if not rows:
        return None
    return min(rows, key=lambda r: (-r["trip_count"], r["year"]))["year"]


def lifetime_stats(trips):
    """人生足迹总览页数据：trips_overview 的全部键 + 里程/在途天数/里程碑/逐年。"""
    overview = trips_overview(trips)
    rows = _year_rows(trips)
    return {
        **overview,
        "total_distance_km": sum(trip_distance_km(t) for t in trips),
        "days_on_road": _days_on_road(trips),
        "milestones": _milestones(trips),
        "by_year": rows,
        "busiest_year": _busiest_year(rows),
    }


def _year_map(year_trips):
    """那年所有旅程的路线叠在一张图上，喂给 story-map.js 的 STORY_MAP.render()。

    不带 day_cities：年度报告没有「按天高亮」，只画全年足迹。
    """
    route, cities, seen = [], [], set()
    for t in year_trips:
        for leg in t.legs:   # Trip.legs 已按 seq 排序
            frm, to = _point(leg.from_city), _point(leg.to_city)
            if frm is None or to is None:
                continue
            route.append({"from": frm, "to": to})
            for p in (frm, to):
                if p["name"] not in seen:
                    seen.add(p["name"])
                    cities.append(dict(p))
    for t in year_trips:
        for d in t.days:
            # 不在任何 Leg 端点上的天也画成点（同 story._map_data 的口径）
            p = _point(d.city)
            if p and p["name"] not in seen:
                seen.add(p["name"])
                cities.append(dict(p))
    return {"route": route, "cities": cities}


def _superlatives(year_trips):
    """年度之最：最贵的一顿饭 / 最贵的一次住宿 / 花得最多的一天 / 走得最远的一趟。"""
    best = {"best_meal": None, "best_stay": None, "biggest_day": None}
    cat_key = {"吃饭": "best_meal", "住宿": "best_stay"}
    for t in year_trips:
        rate_map = {c.currency_code: Decimal(c.rate) for c in t.currencies}
        for d in sorted(t.days, key=lambda x: x.date):
            day_total = Decimal("0.00")
            for e in d.entries:
                cny = to_cny(e.amount, e.currency_code, rate_map)
                day_total += cny
                key = cat_key.get(e.category)
                if key and (best[key] is None or cny > best[key]["cny"]):
                    best[key] = {"title": e.title, "cny": cny, "date": d.date,
                                 "trip_id": t.id, "trip_title": t.title}
            if day_total > 0 and (best["biggest_day"] is None
                                  or day_total > best["biggest_day"]["cny"]):
                best["biggest_day"] = {
                    "cny": day_total, "date": d.date,
                    "city": d.city.name if d.city else None,
                    "trip_id": t.id, "trip_title": t.title,
                }
    best["farthest_trip"] = _farthest_trip(year_trips)
    return best


def year_report(trips, year):
    """某一年的年度报告数据；该年无旅程返回 None（路由据此 404）。"""
    year_trips = _sorted([t for t in trips if t.start_date.year == year])
    if not year_trips:
        return None

    years = sorted({t.start_date.year for t in trips})
    idx = years.index(year)

    total = Decimal("0.00")
    by_category = {cat: Decimal("0.00") for cat in CATEGORIES}
    trip_rows = []
    for t in year_trips:
        s = trip_stats(t)
        total += s["total_cny"]
        for cat in CATEGORIES:
            by_category[cat] += s["by_category"][cat]
        trip_rows.append({
            "id": t.id, "title": t.title,
            "start_date": t.start_date, "end_date": t.end_date,
            "cities": [c.name for c in t.cities],
            "total_cny": s["total_cny"],
        })

    prev_year = years[idx - 1] if idx > 0 else None
    prev_total = None
    if prev_year is not None:
        prev_total = sum((trip_stats(t)["total_cny"] for t in trips
                          if t.start_date.year == prev_year), Decimal("0.00"))

    countries = set()
    for t in year_trips:
        countries |= _trip_countries(t)
    new_countries = sorted(c for c, y in _first_year_by_country(trips).items()
                           if y == year)

    return {
        "year": year,
        "years": years,
        "prev_year": prev_year,
        "next_year": years[idx + 1] if idx < len(years) - 1 else None,
        "trip_count": len(year_trips),
        "country_count": len(countries),
        "total_cny": total,
        "days_on_road": _days_on_road(year_trips),
        "distance_km": sum(trip_distance_km(t) for t in year_trips),
        "map": _year_map(year_trips),
        "new_countries": new_countries,
        "trips": trip_rows,
        "by_category": by_category,
        "prev_total_cny": prev_total,
        "superlatives": _superlatives(year_trips),
    }
