import io
import datetime as dt
from decimal import Decimal
from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord
from tests.expense_xls_helper import make_expense_xls_bytes


def _seed_categories(app):
    with app.app_context():
        food = ExpenseCategory(name="食品酒水", kind="支出")
        db.session.add(food)
        db.session.commit()
        lunch = ExpenseCategory(name="午餐", kind="支出", parent_id=food.id)
        db.session.add(lunch)
        db.session.commit()
        return food.id, lunch.id


def test_list_page_loads_and_shows_seeded_categories(client, app):
    resp = client.get("/expenses/")
    assert resp.status_code == 200
    with app.app_context():
        assert ExpenseCategory.query.filter_by(parent_id=None).count() > 0


def test_create_record_via_form(client, app):
    _, lunch_id = _seed_categories(app)
    resp = client.post("/expenses/new", data={
        "kind": "支出", "date": "2025-06-01", "category_id": str(lunch_id),
        "amount": "35.50", "tag_name": "快餐", "note": "麦当劳",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        r = ExpenseRecord.query.one()
        assert r.amount == Decimal("35.50")
        assert r.tag.name == "快餐"
        assert r.source == "manual"


def test_edit_record(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        r = ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                          amount=Decimal("10.00"), source="manual")
        db.session.add(r)
        db.session.commit()
        rid = r.id
    resp = client.post(f"/expenses/{rid}/edit", data={
        "kind": "支出", "date": "2025-06-02", "category_id": str(lunch_id),
        "amount": "99.00", "tag_name": "", "note": "改过了",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        r = db.session.get(ExpenseRecord, rid)
        assert r.amount == Decimal("99.00")
        assert r.note == "改过了"


def test_delete_record(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        r = ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                          amount=Decimal("10.00"), source="manual")
        db.session.add(r)
        db.session.commit()
        rid = r.id
    resp = client.post(f"/expenses/{rid}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert ExpenseRecord.query.count() == 0


def test_list_filters_by_keyword(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        db.session.add_all([
            ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                         amount=Decimal("10.00"), note="山姆超市", source="manual"),
            ExpenseRecord(kind="支出", date=dt.date(2025, 6, 2), category_id=lunch_id,
                         amount=Decimal("20.00"), note="星巴克", source="manual"),
        ])
        db.session.commit()
    resp = client.get("/expenses/?q=山姆")
    text = resp.get_data(as_text=True)
    assert "山姆超市" in text
    assert "星巴克" not in text


def test_monthly_and_yearly_pages_load(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                                     amount=Decimal("10.00"), source="manual"))
        db.session.commit()
    assert client.get("/expenses/monthly?ym=2025-06").status_code == 200
    assert client.get("/expenses/yearly?year=2025").status_code == 200


def test_import_route_creates_records(client, app):
    content = make_expense_xls_bytes(expense_rows=[
        {"date": "2025-12-31 15:51:51", "cat1": "买买买买", "cat2": "超市市场",
         "amount": 200.7, "merchant": "超市", "note": "山姆"},
    ])
    resp = client.post("/expenses/import",
                       data={"file": (io.BytesIO(content), "bill.xls")},
                       content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert ExpenseRecord.query.count() == 1


def test_category_delete_blocked_when_in_use(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                                     amount=Decimal("10.00"), source="manual"))
        db.session.commit()
    resp = client.post(f"/expenses/categories/{lunch_id}/delete", follow_redirects=True)
    assert "无法删除" in resp.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(ExpenseCategory, lunch_id) is not None


def test_category_delete_allowed_when_unused(client, app):
    top_id, _ = _seed_categories(app)
    with app.app_context():
        empty = ExpenseCategory(name="空分类", kind="支出")
        db.session.add(empty)
        db.session.commit()
        empty_id = empty.id
    resp = client.post(f"/expenses/categories/{empty_id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(ExpenseCategory, empty_id) is None


def test_tag_delete_blocked_when_in_use(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        tag = ExpenseTag(name="超市")
        db.session.add(tag)
        db.session.commit()
        db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                                     amount=Decimal("10.00"), tag_id=tag.id, source="manual"))
        db.session.commit()
        tag_id = tag.id
    resp = client.post(f"/expenses/tags/{tag_id}/delete", follow_redirects=True)
    assert "无法删除" in resp.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(ExpenseTag, tag_id) is not None
