import datetime as dt
from decimal import Decimal
import io
from app.extensions import db
from app.models.trip import Trip, TripCurrency
from app.models.day import Day
from app.services.import_expense import parse_rows, match_row
from tests.xls_helper import make_xls_bytes


def test_parse_rows_reads_date_category_account_amount_title():
    content = make_xls_bytes([
        {"date": "2026-01-20 10:00:00", "category": "旅游餐饮费",
         "account": "现金", "amount": 19.0, "note": "南翔馒头店"},
    ])
    rows = parse_rows(io.BytesIO(content))
    assert rows == [{
        "date": dt.date(2026, 1, 20),
        "category_raw": "旅游餐饮费",
        "account_raw": "现金",
        "amount": Decimal("19.0"),
        "title": "南翔馒头店",
    }]


def _make_trip(app, currencies=None):
    db.create_all()
    t = Trip(title="t", start_date=dt.date(2026, 1, 20), end_date=dt.date(2026, 1, 21))
    t.currencies = [TripCurrency(currency_code=code, rate=Decimal(rate))
                   for code, rate in (currencies or [])]
    db.session.add(t)
    db.session.commit()
    db.session.add(Day(trip_id=t.id, date=dt.date(2026, 1, 20)))
    db.session.commit()
    return db.session.get(Trip, t.id)


def test_match_row_all_fields_resolve(app):
    with app.app_context():
        trip = _make_trip(app)
        row = {"date": dt.date(2026, 1, 20), "category_raw": "旅游餐饮费",
               "account_raw": "现金", "amount": Decimal("19.0"), "title": "南翔馒头店"}
        matched, resolved = match_row(trip, row)
        assert matched is True
        assert resolved["category"] == "吃饭"
        assert resolved["currency_code"] == "CNY"
        assert resolved["day_id"] == trip.days[0].id


def test_match_row_unknown_category_is_unmatched(app):
    with app.app_context():
        trip = _make_trip(app)
        row = {"date": dt.date(2026, 1, 20), "category_raw": "神秘分类",
               "account_raw": "现金", "amount": Decimal("60"), "title": "x"}
        matched, resolved = match_row(trip, row)
        assert matched is False
        assert resolved["category"] is None
        assert resolved["currency_code"] == "CNY"


def test_match_row_date_outside_trip_days_is_unmatched(app):
    with app.app_context():
        trip = _make_trip(app)
        row = {"date": dt.date(2026, 1, 1), "category_raw": "旅游交通费",
               "account_raw": "现金", "amount": Decimal("60"), "title": "保险"}
        matched, resolved = match_row(trip, row)
        assert matched is False
        assert resolved["day_id"] is None
        assert resolved["category"] == "交通"


def test_match_row_undeclared_currency_is_unmatched(app):
    with app.app_context():
        trip = _make_trip(app)  # 没有声明 JPY
        row = {"date": dt.date(2026, 1, 20), "category_raw": "旅游买买买",
               "account_raw": "日元", "amount": Decimal("300"), "title": "和果子"}
        matched, resolved = match_row(trip, row)
        assert matched is False
        assert resolved["currency_code"] is None
        assert resolved["category"] == "购物"


def test_match_row_declared_foreign_currency_matches(app):
    with app.app_context():
        trip = _make_trip(app, currencies=[("JPY", "22.31")])
        row = {"date": dt.date(2026, 1, 20), "category_raw": "旅游买买买",
               "account_raw": "日元", "amount": Decimal("300"), "title": "和果子"}
        matched, resolved = match_row(trip, row)
        assert matched is True
        assert resolved["currency_code"] == "JPY"


def test_parse_rows_skips_non_expense_rows():
    content = make_xls_bytes([
        {"type": "收入", "date": "2026-01-20 10:00:00", "category": "工资",
         "account": "现金", "amount": 5000.0, "note": "退款"},
        {"type": "支出", "date": "2026-01-20 11:00:00", "category": "旅游餐饮费",
         "account": "现金", "amount": 19.0, "note": "南翔馒头店"},
    ])
    rows = parse_rows(io.BytesIO(content))
    assert len(rows) == 1
    assert rows[0]["title"] == "南翔馒头店"
