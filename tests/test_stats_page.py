import datetime as dt
from decimal import Decimal
from app.models.city import City
from app.models.trip import Trip, TripCurrency
from app.models.day import Day, Entry


def test_stats_page_renders(client, app):
    from app.extensions import db
    with app.app_context():
        c = City(name="冲绳")
        t = Trip(title="t", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 1))
        t.currencies = [TripCurrency(currency_code="JPY", rate=Decimal("20"))]
        d = Day(date=dt.date(2026, 1, 1), city=c)
        d.entries = [Entry(category="吃饭", title="拉面", amount=Decimal("2000"),
                           currency_code="JPY")]
        t.days = [d]
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client.get(f"/trips/{tid}/stats")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "吃饭" in body
    assert "100" in body  # 2000/20 = 100 CNY
