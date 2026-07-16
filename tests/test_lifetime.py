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


def test_most_visited_city_first_last_date_across_trips(session):
    """上海被 3 趟不同年份的旅程覆盖：count 与首末到访日期都要对得上。"""
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    sh = make_city(session, "上海", lat=31.23, lng=121.47)
    t1 = make_trip(session, "a", dt.date(2026, 1, 1), dt.date(2026, 1, 2),
                   legs=[(bj, sh)])
    t2 = make_trip(session, "b", dt.date(2024, 1, 1), dt.date(2024, 1, 2),
                   legs=[(bj, sh)])
    t3 = make_trip(session, "c", dt.date(2025, 1, 1), dt.date(2025, 1, 2),
                   legs=[(bj, sh)])
    # 故意乱序传入，验证内部按开始日期排序而非依赖调用方传入顺序
    m = lifetime.lifetime_stats([t1, t2, t3])["milestones"]
    assert m["most_visited_city"]["city"] == "上海"
    assert m["most_visited_city"]["count"] == 3
    assert m["most_visited_city"]["first_date"] == dt.date(2024, 1, 1)
    assert m["most_visited_city"]["last_date"] == dt.date(2026, 1, 1)


def test_most_visited_city_tiebreak_by_name(session):
    """并列时按城市名升序取第一个。"""
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    sh = make_city(session, "上海", lat=31.23, lng=121.47)
    sz = make_city(session, "深圳", lat=22.54, lng=114.06)
    t1 = make_trip(session, "a", dt.date(2025, 1, 1), dt.date(2025, 1, 2),
                   legs=[(bj, sh)])
    t2 = make_trip(session, "b", dt.date(2026, 1, 1), dt.date(2026, 1, 2),
                   legs=[(bj, sz)])
    m = lifetime.lifetime_stats([t1, t2])["milestones"]
    assert m["most_visited_city"]["city"] == "上海"   # "上海" < "深圳"


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


def test_farthest_city_skips_half_coord_city(session):
    """半坐标城市（有纬度、无经度）不该炸 haversine，也不该被当作有效候选。"""
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    half = City(name="残缺市", country="中国", latitude=10.0, longitude=None)
    session.add(half)
    tokyo = make_city(session, "东京", country="日本", lat=35.68, lng=139.69)
    t = make_trip(session, "混合", dt.date(2026, 1, 1), dt.date(2026, 1, 2),
                  legs=[(bj, half), (bj, tokyo)])
    # 不抛异常，且半坐标城市不会成为 farthest_city
    m = lifetime.lifetime_stats([t])["milestones"]
    assert m["farthest_city"]["city"] == "东京"


def test_by_year_fills_gap_years(session):
    c = make_city(session, "上海")
    t1 = make_trip(session, "a", dt.date(2023, 1, 1), dt.date(2023, 1, 2), legs=[(c, c)])
    t2 = make_trip(session, "b", dt.date(2026, 1, 1), dt.date(2026, 1, 2), legs=[(c, c)])
    rows = lifetime.lifetime_stats([t1, t2])["by_year"]
    # 2024、2025 无旅程也要补零，趋势图才看得出停摆
    assert [r["year"] for r in rows] == [2023, 2024, 2025, 2026]
    assert rows[1]["trip_count"] == 0
    assert rows[1]["total_cny"] == Decimal("0.00")
    assert rows[1]["days_on_road"] == 0
    assert rows[1]["new_countries"] == []


def test_cross_year_trip_belongs_to_start_year(session):
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    tp = make_city(session, "台北", country="台湾", lat=25.03, lng=121.57)
    # 2016-12-29 → 2017-01-02：整趟归 2016，不按天拆
    t = make_trip(session, "台北", dt.date(2016, 12, 29), dt.date(2017, 1, 2),
                  legs=[(bj, tp)],
                  days=[(dt.date(2017, 1, 1), tp, [("吃饭", "牛肉面", "100", "CNY")])],
                  currencies=[])
    rows = {r["year"]: r for r in lifetime.lifetime_stats([t])["by_year"]}
    assert rows[2016]["trip_count"] == 1
    assert rows[2016]["days_on_road"] == 5          # 12/29~1/2 整段算 2016
    assert rows[2016]["total_cny"] == Decimal("100.00")   # 2017-01-01 的消费也归 2016
    assert rows[2016]["new_countries"] == ["中国", "台湾"]
    assert 2017 not in rows                          # 只有这一趟，年份跨度到 2016 为止


def test_new_countries_by_first_visit_start_year(session):
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    tokyo = make_city(session, "东京", country="日本", lat=35.68, lng=139.69)
    t1 = make_trip(session, "东京 1", dt.date(2025, 1, 1), dt.date(2025, 1, 2),
                   legs=[(bj, tokyo)])
    t2 = make_trip(session, "东京 2", dt.date(2026, 1, 1), dt.date(2026, 1, 2),
                   legs=[(bj, tokyo)])
    rows = {r["year"]: r for r in lifetime.lifetime_stats([t1, t2])["by_year"]}
    assert rows[2025]["new_countries"] == ["中国", "日本"]
    assert rows[2026]["new_countries"] == []   # 第二次去日本不算新解锁


def test_busiest_year(session):
    c = make_city(session, "上海")
    trips = [
        make_trip(session, "a", dt.date(2025, 1, 1), dt.date(2025, 1, 2), legs=[(c, c)]),
        make_trip(session, "b", dt.date(2026, 1, 1), dt.date(2026, 1, 2), legs=[(c, c)]),
        make_trip(session, "c", dt.date(2026, 3, 1), dt.date(2026, 3, 2), legs=[(c, c)]),
    ]
    assert lifetime.lifetime_stats(trips)["busiest_year"] == 2026


def test_busiest_year_tiebreak_takes_earlier(session):
    c = make_city(session, "上海")
    trips = [
        make_trip(session, "a", dt.date(2025, 1, 1), dt.date(2025, 1, 2), legs=[(c, c)]),
        make_trip(session, "b", dt.date(2025, 3, 1), dt.date(2025, 3, 2), legs=[(c, c)]),
        make_trip(session, "c", dt.date(2026, 1, 1), dt.date(2026, 1, 2), legs=[(c, c)]),
        make_trip(session, "d", dt.date(2026, 3, 1), dt.date(2026, 3, 2), legs=[(c, c)]),
    ]
    # 2025、2026 各 2 趟，并列取较早的 2025
    assert lifetime.lifetime_stats(trips)["busiest_year"] == 2025


def test_by_year_empty(session):
    s = lifetime.lifetime_stats([])
    assert s["by_year"] == []
    assert s["busiest_year"] is None


def test_year_report_sections(session):
    bj = make_city(session, "北京", lat=39.90, lng=116.41)
    tokyo = make_city(session, "东京", country="日本", lat=35.68, lng=139.69)
    prev = make_trip(session, "去年", dt.date(2025, 6, 1), dt.date(2025, 6, 2),
                     legs=[(bj, bj)],
                     days=[(dt.date(2025, 6, 1), bj, [("购物", "书", "50", "CNY")])])
    t = make_trip(
        session, "东京", dt.date(2026, 4, 1), dt.date(2026, 4, 3),
        legs=[(bj, tokyo)],
        days=[
            (dt.date(2026, 4, 1), tokyo, [("吃饭", "寿司", "4000", "JPY"),
                                          ("住宿", "酒店", "6000", "JPY")]),
            (dt.date(2026, 4, 2), tokyo, [("吃饭", "拉面", "2000", "JPY")]),
        ],
        currencies=[("JPY", "20")],
    )
    r = lifetime.year_report([prev, t], 2026)

    # 第 1 节 封面
    assert r["year"] == 2026
    assert r["trip_count"] == 1
    assert r["country_count"] == 2          # 中国 + 日本
    assert r["days_on_road"] == 3
    assert r["total_cny"] == Decimal("600.00")   # (4000+6000+2000)/20
    # 年份切换器
    assert r["years"] == [2025, 2026]
    assert r["prev_year"] == 2025
    assert r["next_year"] is None
    # 第 2 节 地图
    assert {c["name"] for c in r["map"]["cities"]} == {"北京", "东京"}
    assert len(r["map"]["route"]) == 1
    # 第 3 节 新解锁国家
    assert r["new_countries"] == ["日本"]   # 中国在 2025 已解锁
    # 第 4 节 旅程清单
    assert [x["id"] for x in r["trips"]] == [t.id]
    assert r["trips"][0]["total_cny"] == Decimal("600.00")
    # 第 5 节 花费构成 + 同比
    assert r["by_category"]["吃饭"] == Decimal("300.00")
    assert r["by_category"]["住宿"] == Decimal("300.00")
    assert r["prev_total_cny"] == Decimal("50.00")
    # 第 6 节 年度之最
    s = r["superlatives"]
    assert s["best_meal"]["title"] == "寿司"
    assert s["best_meal"]["cny"] == Decimal("200.00")
    assert s["best_stay"]["title"] == "酒店"
    assert s["biggest_day"]["date"] == dt.date(2026, 4, 1)   # 500 > 100
    assert s["biggest_day"]["cny"] == Decimal("500.00")
    assert s["farthest_trip"]["trip_id"] == t.id


def test_year_report_missing_year(session):
    c = make_city(session, "上海")
    t = make_trip(session, "a", dt.date(2026, 1, 1), dt.date(2026, 1, 2), legs=[(c, c)])
    assert lifetime.year_report([t], 2020) is None
    assert lifetime.year_report([], 2026) is None


def test_year_report_prev_total_none_when_no_prev_year(session):
    c = make_city(session, "上海")
    t = make_trip(session, "a", dt.date(2026, 1, 1), dt.date(2026, 1, 2), legs=[(c, c)])
    r = lifetime.year_report([t], 2026)
    assert r["prev_total_cny"] is None
    assert r["prev_year"] is None


def test_year_report_superlatives_none_without_entries(session):
    c = make_city(session, "上海")
    t = make_trip(session, "a", dt.date(2026, 1, 1), dt.date(2026, 1, 2), legs=[(c, c)])
    s = lifetime.year_report([t], 2026)["superlatives"]
    assert s["best_meal"] is None
    assert s["best_stay"] is None
    assert s["biggest_day"] is None
    assert s["farthest_trip"] is None


def test_year_report_prev_year_skips_gap_year(session):
    """2020 空档：2021 的同比取最近一个有旅程的年份（2019），而非严格意义的「上一年」。"""
    c = make_city(session, "上海")
    t2019 = make_trip(session, "a", dt.date(2019, 1, 1), dt.date(2019, 1, 2),
                      legs=[(c, c)],
                      days=[(dt.date(2019, 1, 1), c, [("购物", "书", "80", "CNY")])])
    t2021 = make_trip(session, "b", dt.date(2021, 1, 1), dt.date(2021, 1, 2), legs=[(c, c)])
    r = lifetime.year_report([t2019, t2021], 2021)
    assert r["prev_year"] == 2019
    assert r["prev_total_cny"] == Decimal("80.00")
