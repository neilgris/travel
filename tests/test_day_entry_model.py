import datetime as dt
from decimal import Decimal
from app.models.trip import Trip
from app.models.city import City
from app.models.day import Day, Entry, EntryImage


def test_day_entry_image(session):
    c = City(name="香港"); session.add(c)
    t = Trip(title="x", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,2))
    session.add(t); session.commit()
    d = Day(trip_id=t.id, date=dt.date(2026,1,1), city=c, diary="抵达")
    e = Entry(category="吃饭", title="茶餐厅", amount=Decimal("120.00"),
              currency_code="HKD")
    e.images = [EntryImage(path="uploads/a.jpg")]
    d.entries = [e]
    session.add(d); session.commit()
    assert t.days[0].entries[0].images[0].path == "uploads/a.jpg"
    assert t.days[0].city.name == "香港"
