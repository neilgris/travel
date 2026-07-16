import datetime as dt
from decimal import Decimal

from app.models.city import City
from app.models.day import Day, Entry
from app.models.trip import Trip, TripCurrency, Leg
from app.services import lifetime


def make_city(session, name, country="中国", lat=None, lng=None):
    c = City(name=name, country=country, latitude=lat, longitude=lng)
    session.add(c)
    session.flush()
    return c


def make_trip(session, title, start, end, legs=(), days=(), currencies=()):
    """legs: [(from_city, to_city)]；days: [(date, city, [(类别, 标题, 金额, 币种)])]"""
    t = Trip(title=title, start_date=start, end_date=end)
    t.currencies = [TripCurrency(currency_code=code, rate=Decimal(rate))
                    for code, rate in currencies]
    t.legs = [Leg(seq=i, from_city=f, to_city=to, transport_mode="飞机")
              for i, (f, to) in enumerate(legs)]
    day_objs = []
    for date, city, entries in days:
        d = Day(date=date, city=city)
        d.entries = [Entry(category=cat, title=title_, amount=Decimal(amt),
                           currency_code=cur)
                     for cat, title_, amt, cur in entries]
        day_objs.append(d)
    t.days = day_objs
    session.add(t)
    session.commit()
    return t


def test_lifetime_stats_totals(session):
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    okinawa = make_city(session, "冲绳", country="日本", lat=26.21, lng=127.68)
    t = make_trip(
        session, "冲绳", dt.date(2026, 1, 1), dt.date(2026, 1, 3),
        legs=[(bj, okinawa)],
        days=[(dt.date(2026, 1, 1), okinawa, [("吃饭", "拉面", "2000", "JPY")])],
        currencies=[("JPY", "20")],
    )
    s = lifetime.lifetime_stats([t])
    # 透传 trips_overview
    assert s["trip_count"] == 1
    assert s["grand_total"] == Decimal("100.00")   # 2000 JPY / 20
    assert s["country_count"] == 2                 # 中国 + 日本
    # 新增：里程与在途天数
    assert s["total_distance_km"] > 0
    assert s["days_on_road"] == 3                  # 1/1 ~ 1/3 含首尾


def test_days_on_road_dedupes_overlap(session):
    c = make_city(session, "上海")
    t1 = make_trip(session, "a", dt.date(2026, 3, 1), dt.date(2026, 3, 3))
    t2 = make_trip(session, "b", dt.date(2026, 3, 3), dt.date(2026, 3, 4))
    # 3/1,3/2,3/3 + 3/3,3/4 → 3/3 只算一次 → 4 天
    assert lifetime.lifetime_stats([t1, t2])["days_on_road"] == 4


def test_lifetime_stats_empty(session):
    s = lifetime.lifetime_stats([])
    assert s["trip_count"] == 0
    assert s["days_on_road"] == 0
    assert s["total_distance_km"] == 0
