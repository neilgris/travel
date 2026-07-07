import datetime as dt
from decimal import Decimal
from app.models.trip import Trip
from app.models.city import City
from app.models.day import Day, Entry, DayImage


def test_day_image_and_entry(session):
    c = City(name="香港")
    session.add(c)
    t = Trip(title="x", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,2))
    session.add(t)
    session.commit()
    d = Day(trip_id=t.id, date=dt.date(2026,1,1), city=c, diary="抵达")
    e = Entry(category="吃饭", title="茶餐厅", amount=Decimal("120.00"),
              currency_code="HKD")
    d.entries = [e]
    d.images = [DayImage(path="uploads/a.jpg")]
    session.add(d); session.commit()
    # 配图挂在「天」上，不再挂在消费条目上。
    assert t.days[0].images[0].path == "uploads/a.jpg"
    assert t.days[0].entries[0].title == "茶餐厅"
    assert t.days[0].city.name == "香港"


def test_other_expense_is_a_valid_category():
    from app.models.day import CATEGORIES
    assert CATEGORIES == ["吃饭", "游玩", "购物", "住宿", "交通", "其他消费"]
