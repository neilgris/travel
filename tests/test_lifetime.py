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


def test_milestones(session):
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    tokyo = make_city(session, "东京", country="日本", lat=35.68, lng=139.69)
    nyc = make_city(session, "纽约", country="美国", lat=40.71, lng=-74.01)
    # 2024 国内游（3 天）；2025 东京（2 天）；2026 纽约（5 天，最远最长）
    t1 = make_trip(session, "国内", dt.date(2024, 5, 1), dt.date(2024, 5, 3),
                   legs=[(bj, bj)])
    t2 = make_trip(session, "东京", dt.date(2025, 5, 1), dt.date(2025, 5, 2),
                   legs=[(bj, tokyo)])
    t3 = make_trip(session, "纽约", dt.date(2026, 5, 1), dt.date(2026, 5, 5),
                   legs=[(bj, nyc)])
    m = lifetime.lifetime_stats([t1, t2, t3])["milestones"]

    assert m["first_abroad"]["trip_id"] == t2.id      # 东京是最早的出国
    assert m["first_abroad"]["countries"] == ["日本"]
    assert m["farthest_trip"]["trip_id"] == t3.id     # 北京→纽约最远
    assert m["longest_trip"]["trip_id"] == t3.id      # 5 天
    assert m["longest_trip"]["days"] == 5
    assert m["farthest_city"]["city"] == "纽约"
    assert m["farthest_city"]["distance_km"] > 10000


def test_most_visited_city_excludes_home(session):
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    sh = make_city(session, "上海", lat=31.23, lng=121.47)
    # 北京出现 2 次、上海 1 次，但北京是住处要排除 → 上海胜出
    t1 = make_trip(session, "a", dt.date(2025, 1, 1), dt.date(2025, 1, 2),
                   legs=[(bj, sh)])
    t2 = make_trip(session, "b", dt.date(2026, 1, 1), dt.date(2026, 1, 2),
                   legs=[(bj, bj)])
    m = lifetime.lifetime_stats([t1, t2])["milestones"]
    assert m["most_visited_city"]["city"] == "上海"
    assert m["most_visited_city"]["count"] == 1
    assert m["most_visited_city"]["first_date"] == dt.date(2025, 1, 1)
    assert m["most_visited_city"]["last_date"] == dt.date(2025, 1, 1)


def test_milestones_none_when_data_missing(session):
    # 只有国内游、且城市无坐标 → 出国/最远旅程/最远城市都无从谈起
    c = make_city(session, "天津")
    t = make_trip(session, "a", dt.date(2026, 1, 1), dt.date(2026, 1, 1),
                  legs=[(c, c)])
    m = lifetime.lifetime_stats([t])["milestones"]
    assert m["first_abroad"] is None
    assert m["farthest_trip"] is None      # 无坐标 → 里程 0 → 不算里程碑
    assert m["farthest_city"] is None      # 库里无北京 → 无基准
    assert m["longest_trip"]["days"] == 1  # 这个总有


def test_milestones_empty(session):
    m = lifetime.lifetime_stats([])["milestones"]
    assert all(v is None for v in m.values())
