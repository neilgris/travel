import datetime as dt
from decimal import Decimal
from app.extensions import db
from app.models.city import City
from app.models.trip import Trip, TripCurrency
from app.models.day import Day, Entry


def make_trip(app):
    from app.extensions import db
    with app.app_context():
        c = City(name="香港")
        t = Trip(title="t", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 3))
        t.currencies = [TripCurrency(currency_code="HKD", rate=Decimal("1.1"))]
        db.session.add_all([c, t])
        db.session.commit()
        return t.id, c.id


def test_add_entry_mismatched_trip_day_returns_404(client, app):
    # Create two separate trips; a day under trip B; POST entry to trip A's URL
    with app.app_context():
        c = City(name="上海")
        ta = Trip(title="旅程A", start_date=dt.date(2026, 2, 1), end_date=dt.date(2026, 2, 3))
        tb = Trip(title="旅程B", start_date=dt.date(2026, 3, 1), end_date=dt.date(2026, 3, 3))
        db.session.add_all([c, ta, tb])
        db.session.commit()
        day_b = Day(trip_id=tb.id, date=dt.date(2026, 3, 1))
        db.session.add(day_b)
        db.session.commit()
        ta_id = ta.id
        day_b_id = day_b.id
    resp = client.post(f"/trips/{ta_id}/days/{day_b_id}/entries", data={
        "category": "吃饭", "title": "测试", "amount": "10", "currency_code": "CNY",
    })
    assert resp.status_code == 404


def test_add_day_and_entry(client, app):
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={
        "date": "2026-01-01", "city_id": str(cid), "diary": "抵达香港"},
        follow_redirects=True)
    with app.app_context():
        day = Day.query.filter_by(trip_id=tid).one()
        did = day.id
    resp = client.post(f"/trips/{tid}/days/{did}/entries", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120",
        "currency_code": "HKD", "description": "好吃"},
        follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        e = Entry.query.filter_by(title="茶餐厅").one()
        assert str(e.amount) == "120.00" and e.category == "吃饭"
