from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from app.models.day import CATEGORIES

TWO = Decimal("0.01")


def to_cny(amount, currency_code, rate_map):
    amount = Decimal(amount)
    if currency_code == "CNY":
        cny = amount
    elif currency_code in rate_map:
        rate = Decimal(rate_map[currency_code])
        cny = amount / rate
    else:
        # Defensive: UI constrains entry currency to CNY + trip.currencies, so an unconfigured code should not reach here; treat as 0 rather than crash.
        cny = Decimal("0.00")
    return cny.quantize(TWO, rounding=ROUND_HALF_UP)


NO_CITY = "未指定"


def trip_stats(trip):
    rate_map = {c.currency_code: Decimal(c.rate) for c in trip.currencies}
    total = Decimal("0.00")
    by_category = {cat: Decimal("0.00") for cat in CATEGORIES}
    by_day = []
    by_currency = {}
    by_city = {}
    top_entries = []
    for day in sorted(trip.days, key=lambda d: d.date):
        day_total = Decimal("0.00")
        city_name = day.city.name if day.city else NO_CITY
        for e in day.entries:
            # Accumulate per-entry rounded CNY so total_cny, by_category, by_day, by_currency stay mutually consistent.
            cny = to_cny(e.amount, e.currency_code, rate_map)
            total += cny
            day_total += cny
            by_category[e.category] += cny
            cur = by_currency.setdefault(
                e.currency_code, {"code": e.currency_code,
                                  "original": Decimal("0.00"), "cny": Decimal("0.00")})
            cur["original"] += Decimal(e.amount)
            cur["cny"] += cny
            by_city[city_name] = by_city.get(city_name, Decimal("0.00")) + cny
            top_entries.append({
                "title": e.title, "category": e.category, "cny": cny,
                "date": day.date, "currency_code": e.currency_code,
                "original": Decimal(e.amount),
            })
        by_day.append({"date": day.date, "total_cny": day_total})

    # 累计花费：按已排序的 by_day 逐日累加。
    cumulative = []
    running = Decimal("0.00")
    for d in by_day:
        running += d["total_cny"]
        cumulative.append({"date": d["date"], "total_cny": running})

    by_city_list = sorted(
        ({"city": name, "cny": cny} for name, cny in by_city.items()),
        key=lambda x: x["cny"], reverse=True)
    top_entries.sort(key=lambda x: x["cny"], reverse=True)

    # 按类别分组的消费明细（含日期、城市），用于环图点击后右侧面板展示
    by_category_detail = {cat: [] for cat in CATEGORIES}
    for day in sorted(trip.days, key=lambda d: d.date):
        city_name = day.city.name if day.city else NO_CITY
        for e in day.entries:
            cny = to_cny(e.amount, e.currency_code, rate_map)
            by_category_detail[e.category].append({
                "title": e.title,
                "cny": cny,
                "date": day.date,
                "city": city_name,
            })
    for cat in by_category_detail:
        by_category_detail[cat].sort(key=lambda x: x["cny"], reverse=True)

    return {
        "total_cny": total,
        "by_category": by_category,
        "by_day": by_day,
        "by_currency": list(by_currency.values()),
        "by_city": by_city_list,
        "cumulative": cumulative,
        "top_entries": top_entries[:20],
        "by_category_detail": by_category_detail,
    }


def trips_overview(trips):
    """跨旅程消费对比看板数据：复用 trip_stats 逐趟统计后聚合。

    trips 为任意顺序的 Trip 列表；返回的 trips 列表按总花费降序（=花费排名）。
    """
    grand_total = Decimal("0.00")
    global_by_category = {cat: Decimal("0.00") for cat in CATEGORIES}
    cities = set()
    city_names = {}
    city_visits = Counter()
    countries = set()
    country_cities = {}
    rows = []
    for t in trips:
        s = trip_stats(t)
        grand_total += s["total_cny"]
        for cat in CATEGORIES:
            global_by_category[cat] += s["by_category"][cat]
        trip_city_ids = set()
        for c in t.cities:
            cities.add(c.id)
            city_names[c.id] = c.name
            trip_city_ids.add(c.id)
            if c.country:
                countries.add(c.country)
                country_cities.setdefault(c.country, set()).add(c.id)
        city_visits.update(trip_city_ids)
        rows.append({
            "id": t.id,
            "title": t.title,
            "start_date": t.start_date,
            "end_date": t.end_date,
            "total_cny": s["total_cny"],
            "by_category": s["by_category"],
            "top_entries": s["top_entries"],
        })

    rows.sort(key=lambda r: r["total_cny"], reverse=True)

    def _card(r):
        return {"id": r["id"], "title": r["title"], "total_cny": r["total_cny"],
                "by_category": r["by_category"], "top_entries": r["top_entries"]}

    nonzero_rows = [r for r in rows if r["total_cny"] > 0]
    most_expensive = _card(rows[0]) if rows else None
    cheapest = _card(nonzero_rows[-1]) if nonzero_rows else None

    # 到访城市 Top 5（按覆盖旅程数降序），排除北京（住处所在地，去掉才有对比意义）
    top_cities = [
        {"city": city_names[cid], "count": n}
        for cid, n in sorted(city_visits.items(), key=lambda x: (-x[1], city_names[x[0]]))
        if city_names[cid] != "北京"
    ][:5]

    return {
        "grand_total": grand_total,
        "trip_count": len(rows),
        "city_count": len(cities),
        "top_cities": top_cities,
        "country_count": len(countries),
        "countries": sorted(countries, key=lambda c: (-len(country_cities[c]), c)),
        "global_by_category": global_by_category,
        "most_expensive": most_expensive,
        "cheapest": cheapest,
        "trips": rows,
    }
