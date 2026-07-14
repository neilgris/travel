import datetime as dt
from decimal import Decimal

from app.models.city import City
from app.models.trip import Trip, TripCurrency
from app.models.day import Day, Entry, DayImage
from app.services.story import story_data


def _mk_trip(session, **kw):
    t = Trip(title=kw.get("title", "行"),
             start_date=kw.get("start", dt.date(2026, 1, 1)),
             end_date=kw.get("end", dt.date(2026, 1, 3)))
    session.add(t)
    return t


def test_days_basic_content(session):
    t = _mk_trip(session)
    c = City(name="东京", latitude=35.6, longitude=139.7)
    d = Day(date=dt.date(2026, 1, 1), city=c, diary="到东京，吃拉面")
    d.images = [DayImage(path="uploads/trips/9/a.jpg"),
                DayImage(path="uploads/trips/9/b.jpg")]
    t.days = [d]
    session.add(c)
    session.commit()

    days = story_data(t)["days"]
    assert len(days) == 1
    assert days[0]["date"] == dt.date(2026, 1, 1)
    assert days[0]["city_name"] == "东京"
    assert days[0]["journal"] == "到东京，吃拉面"
    assert days[0]["images"] == ["trips/9/a.jpg", "trips/9/b.jpg"]


def test_highlights_top3_by_cny_desc(session):
    t = _mk_trip(session)
    t.currencies = [TripCurrency(currency_code="JPY", rate=Decimal("20"))]
    d = Day(date=dt.date(2026, 1, 1))
    d.entries = [
        Entry(category="吃饭", title="拉面", amount=Decimal("1600"), currency_code="JPY"),  # 80
        Entry(category="购物", title="手办", amount=Decimal("6000"), currency_code="JPY"),  # 300
        Entry(category="游玩", title="门票", amount=Decimal("1000"), currency_code="JPY"),  # 50
        Entry(category="交通", title="地铁", amount=Decimal("400"), currency_code="JPY"),   # 20
    ]
    t.days = [d]
    session.commit()

    day = story_data(t)["days"][0]
    assert day["spend_cny"] == Decimal("450.00")  # 100+300+50+20 各已按条四舍五入
    titles = [h["title"] for h in day["highlights"]]
    assert titles == ["手办", "拉面", "门票"]  # 前 3，降序
    assert day["highlights"][0]["cny"] == Decimal("300.00")


def test_day_without_entries_or_diary(session):
    t = _mk_trip(session)
    d = Day(date=dt.date(2026, 1, 2))  # 无城市、无日记、无消费、无图
    t.days = [d]
    session.commit()

    day = story_data(t)["days"][0]
    assert day["city_name"] is None
    assert day["journal"] is None
    assert day["images"] == []
    assert day["spend_cny"] == Decimal("0.00")
    assert day["highlights"] == []
