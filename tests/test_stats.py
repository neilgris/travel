import datetime as dt
from decimal import Decimal
from app.models.trip import Trip, TripCurrency
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
