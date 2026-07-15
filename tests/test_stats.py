import datetime as dt
from decimal import Decimal
from app.models.trip import Trip, TripCurrency, Leg
from app.models.city import City
from app.models.day import Day, Entry
from app.services import stats


def build_trip(session):
    c = City(name="冲绳")
    session.add(c)
    t = Trip(title="x", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 2))
    t.currencies = [TripCurrency(currency_code="JPY", rate=Decimal("20"))]  # 1 CNY = 20 JPY
    d1 = Day(date=dt.date(2026, 1, 1), city=c)
    d1.entries = [
        Entry(category="吃饭", title="拉面", amount=Decimal("2000"), currency_code="JPY"),
        Entry(category="购物", title="手办", amount=Decimal("100"), currency_code="CNY"),
    ]
    d2 = Day(date=dt.date(2026, 1, 2), city=c)
    d2.entries = [Entry(category="吃饭", title="寿司", amount=Decimal("4000"), currency_code="JPY")]
    t.days = [d1, d2]
    session.add(t)
    session.commit()
    return t


def test_to_cny():
    rate_map = {"JPY": Decimal("20")}
    assert stats.to_cny(Decimal("2000"), "JPY", rate_map) == Decimal("100.00")
    assert stats.to_cny(Decimal("100"), "CNY", rate_map) == Decimal("100.00")


def test_trip_stats(session):
    t = build_trip(session)
    s = stats.trip_stats(t)
    # 2000JPY/20 + 100CNY + 4000JPY/20 = 100 + 100 + 200 = 400
    assert s["total_cny"] == Decimal("400.00")
    assert s["by_category"]["吃饭"] == Decimal("300.00")
    assert s["by_category"]["购物"] == Decimal("100.00")
    assert s["by_day"][0]["total_cny"] == Decimal("200.00")
    assert s["by_day"][1]["total_cny"] == Decimal("200.00")
    jpy = next(x for x in s["by_currency"] if x["code"] == "JPY")
    assert jpy["original"] == Decimal("6000")
    assert jpy["cny"] == Decimal("300.00")
    # top_entries 取前 20
    assert len(s["top_entries"]) <= 20
    # by_category_detail: 每个类别含消费明细列表，按价格降序
    assert "by_category_detail" in s
    eat_detail = s["by_category_detail"]["吃饭"]
    assert len(eat_detail) == 2
    # 寿司 200 CNY > 拉面 100 CNY
    assert eat_detail[0]["title"] == "寿司"
    assert eat_detail[0]["cny"] == Decimal("200.00")
    assert eat_detail[1]["title"] == "拉面"
    assert eat_detail[1]["cny"] == Decimal("100.00")
    shop_detail = s["by_category_detail"]["购物"]
    assert len(shop_detail) == 1
    assert shop_detail[0]["title"] == "手办"


def test_trips_overview_top_cities(session):
    def city(name):
        c = City.query.filter_by(name=name).first()
        if not c:
            c = City(name=name)
            session.add(c)
        return c

    def trip_via(idx, to_name):
        t = Trip(title=f"t{idx}", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 1))
        t.legs = [Leg(seq=1, from_city=city("北京"), to_city=city(to_name), transport_mode="飞机")]
        session.add(t)
        return t

    # 北京 出现 12 次(每趟必经)理应被排除；其余城市次数：上海4/香港3/东京2/大阪2/台北1/首尔1
    dests = (["上海"] * 4 + ["香港"] * 3 + ["东京"] * 2 + ["大阪"] * 2 + ["台北"] + ["首尔"])
    trips = [trip_via(i, name) for i, name in enumerate(dests)]
    session.commit()

    overview = stats.trips_overview(trips)
    # 北京虽出现在全部 12 趟里，但被排除在外
    assert "北京" not in [c["city"] for c in overview["top_cities"]]
    # 按次数降序，同次数按城市名排序，取前 5
    assert overview["top_cities"] == [
        {"city": "上海", "count": 4},
        {"city": "香港", "count": 3},
        {"city": "东京", "count": 2},
        {"city": "大阪", "count": 2},
        {"city": "台北", "count": 1},
    ]


def test_trips_overview_cheapest_excludes_zero_spend(session):
    t_zero = Trip(title="无消费旅程", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 1))
    session.add(t_zero)
    t_real = build_trip(session)  # 总花费 400

    overview = stats.trips_overview([t_zero, t_real])
    assert overview["cheapest"]["id"] == t_real.id
    assert overview["cheapest"]["total_cny"] == Decimal("400.00")
