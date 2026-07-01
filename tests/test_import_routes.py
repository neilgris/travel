import datetime as dt
from decimal import Decimal
import io
from app.extensions import db
from app.models.trip import Trip, TripCurrency
from app.models.city import City
from app.models.day import Day, Entry
from tests.xls_helper import make_xls_bytes


def make_trip_with_days(app):
    with app.app_context():
        c = City(name="香港")
        t = Trip(title="202601", start_date=dt.date(2026, 1, 20), end_date=dt.date(2026, 1, 21))
        t.currencies = [TripCurrency(currency_code="HKD", rate=Decimal("1.12"))]
        db.session.add_all([c, t])
        db.session.commit()
        db.session.add_all([
            Day(trip_id=t.id, date=dt.date(2026, 1, 20), city_id=c.id),
            Day(trip_id=t.id, date=dt.date(2026, 1, 21), city_id=c.id),
        ])
        db.session.commit()
        return t.id


def test_import_auto_creates_matched_entry(client, app):
    tid = make_trip_with_days(app)
    content = make_xls_bytes([
        {"date": "2026-01-20 10:00:00", "category": "旅游餐饮费",
         "account": "现金", "amount": 19.0, "note": "南翔馒头店"},
    ])
    resp = client.post(f"/trips/{tid}/import",
                       data={"file": (io.BytesIO(content), "bill.xls")},
                       content_type="multipart/form-data",
                       follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        e = Entry.query.filter_by(title="南翔馒头店").one()
        assert e.category == "吃饭"
        assert e.currency_code == "CNY"
        assert str(e.amount) == "19.00"


def test_import_shows_unmatched_row_and_does_not_create_entry(client, app):
    tid = make_trip_with_days(app)
    content = make_xls_bytes([
        {"date": "2026-01-01 10:00:00", "category": "旅游交通费",
         "account": "现金", "amount": 60.0, "note": "提前买的保险"},
    ])
    resp = client.post(f"/trips/{tid}/import",
                       data={"file": (io.BytesIO(content), "bill.xls")},
                       content_type="multipart/form-data")
    assert resp.status_code == 200
    assert "提前买的保险" in resp.get_data(as_text=True)
    with app.app_context():
        assert Entry.query.filter_by(title="提前买的保险").count() == 0


def test_import_confirm_creates_entry_for_unmatched_row(client, app):
    tid = make_trip_with_days(app)
    with app.app_context():
        day_id = Day.query.filter_by(trip_id=tid, date=dt.date(2026, 1, 20)).one().id
    resp = client.post(f"/trips/{tid}/import/confirm", data={
        "title": "提前买的保险", "amount": "60.0",
        "day_id": str(day_id), "category": "交通", "currency_code": "CNY",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        e = Entry.query.filter_by(title="提前买的保险").one()
        assert e.category == "交通"
        assert e.day_id == day_id


def test_import_confirm_skips_incomplete_row(client, app):
    tid = make_trip_with_days(app)
    resp = client.post(f"/trips/{tid}/import/confirm", data={
        "title": "没选日期的记录", "amount": "10.0",
        "day_id": "", "category": "交通", "currency_code": "CNY",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Entry.query.filter_by(title="没选日期的记录").count() == 0
