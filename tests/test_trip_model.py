import datetime as dt
from app.models.trip import Trip, Leg, TripCurrency
from app.models.city import City
from app.models.person import Person

def make_cities(session):
    bj = City(name="北京"); hk = City(name="香港"); ok = City(name="冲绳")
    session.add_all([bj, hk, ok]); session.commit()
    return bj, hk, ok

def test_trip_with_legs_derives_cities_and_modes(session):
    bj, hk, ok = make_cities(session)
    t = Trip(title="测试行程", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,5))
    t.legs = [
        Leg(seq=1, from_city=bj, to_city=hk, transport_mode="飞机"),
        Leg(seq=2, from_city=hk, to_city=ok, transport_mode="游轮"),
    ]
    session.add(t); session.commit()
    assert [c.name for c in t.cities] == ["北京", "香港", "冲绳"]
    assert t.transport_modes == ["飞机", "游轮"]

def test_trip_currencies_and_people(session):
    bj, hk, ok = make_cities(session)
    p = Person(name="老婆"); session.add(p)
    t = Trip(title="x", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,2))
    t.currencies = [TripCurrency(currency_code="JPY", rate=20.8)]
    t.people = [p]
    session.add(t); session.commit()
    assert t.currencies[0].currency_code == "JPY"
    assert t.people[0].name == "老婆"
