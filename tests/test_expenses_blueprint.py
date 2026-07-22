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


def test_edit_get_xhr_returns_inline_form_fragment(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        r = ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                          amount=Decimal("10.00"), source="manual")
        db.session.add(r)
        db.session.commit()
        rid = r.id
    resp = client.get(f"/expenses/{rid}/edit", headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "exp-inline-form" in text
    assert "<html" not in text.lower()  # 只返回片段，不是整页


def test_edit_post_xhr_returns_json_with_updated_row_html(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        r = ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                          amount=Decimal("10.00"), source="manual")
        db.session.add(r)
        db.session.commit()
        rid = r.id
    resp = client.post(f"/expenses/{rid}/edit", data={
        "kind": "支出", "date": "2025-06-02", "category_id": str(lunch_id),
        "amount": "99.00", "tag_name": "", "note": "异步改过了",
    }, headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "异步改过了" in data["html"]
    with app.app_context():
        r = db.session.get(ExpenseRecord, rid)
        assert r.amount == Decimal("99.00")
        assert r.note == "异步改过了"


def test_edit_post_xhr_with_bad_category_returns_json_error(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        r = ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                          amount=Decimal("10.00"), source="manual")
        db.session.add(r)
        db.session.commit()
        rid = r.id
    resp = client.post(f"/expenses/{rid}/edit", data={
        "kind": "支出", "date": "2025-06-02", "category_id": "999999",
        "amount": "99.00", "tag_name": "", "note": "不应该保存",
    }, headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["error"]
    with app.app_context():
        r = db.session.get(ExpenseRecord, rid)
        assert r.note is None


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


def test_list_filters_by_empty_tag(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        tag = ExpenseTag(name="聚餐")
        db.session.add(tag)
        db.session.commit()
        db.session.add_all([
            ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                         amount=Decimal("10.00"), note="无标签这条", source="manual"),
            ExpenseRecord(kind="支出", date=dt.date(2025, 6, 2), category_id=lunch_id,
                         amount=Decimal("20.00"), note="有标签这条", tag_id=tag.id, source="manual"),
        ])
        db.session.commit()
    resp = client.get("/expenses/?tag_id=0")
    text = resp.get_data(as_text=True)
    assert "无标签这条" in text
    assert "有标签这条" not in text


def test_monthly_and_yearly_pages_load(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=lunch_id,
                                     amount=Decimal("10.00"), source="manual"))
        db.session.commit()
    assert client.get("/expenses/monthly?ym=2025-06").status_code == 200
    assert client.get("/expenses/yearly?year=2025").status_code == 200


def test_overview_page_loads_with_and_without_data(client, app):
    # 空库也不能报错
    assert client.get("/expenses/overview").status_code == 200
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        db.session.add(ExpenseRecord(kind="支出", date=dt.date(2023, 6, 1), category_id=lunch_id,
                                     amount=Decimal("10.00"), source="manual"))
        db.session.add(ExpenseRecord(kind="支出", date=dt.date(2024, 6, 1), category_id=lunch_id,
                                     amount=Decimal("20.00"), source="manual"))
        db.session.commit()
    resp = client.get("/expenses/overview")
    assert resp.status_code == 200
    assert "整体统计" in resp.get_data(as_text=True)


def test_clear_by_year_only_removes_that_year(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        db.session.add_all([
            ExpenseRecord(kind="支出", date=dt.date(2023, 6, 1), category_id=lunch_id,
                         amount=Decimal("10.00"), source="manual"),
            ExpenseRecord(kind="支出", date=dt.date(2024, 6, 1), category_id=lunch_id,
                         amount=Decimal("20.00"), source="manual"),
        ])
        db.session.commit()
    resp = client.post("/expenses/clear", data={"year": "2023"}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        remaining = ExpenseRecord.query.all()
        assert len(remaining) == 1
        assert remaining[0].date.year == 2024


def test_clear_all_removes_every_record(client, app):
    _, lunch_id = _seed_categories(app)
    with app.app_context():
        db.session.add_all([
            ExpenseRecord(kind="支出", date=dt.date(2023, 6, 1), category_id=lunch_id,
                         amount=Decimal("10.00"), source="manual"),
            ExpenseRecord(kind="支出", date=dt.date(2024, 6, 1), category_id=lunch_id,
                         amount=Decimal("20.00"), source="manual"),
        ])
        db.session.commit()
    resp = client.post("/expenses/clear", data={"year": ""}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert ExpenseRecord.query.count() == 0


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


def test_create_category_without_icon_autofills_known_name(client, app):
    # "人情往来" 在 CATEGORY_ICONS 里有已知图标，但不在默认 seed 列表里，
    # 确保测的是「新建时自动补图标」而非撞见 seed 数据。
    resp = client.post("/expenses/categories", data={
        "name": "人情往来", "kind": "支出", "parent_id": "",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        cat = ExpenseCategory.query.filter_by(name="人情往来", parent_id=None).one()
        assert cat.icon == "🧧"


def test_create_category_without_icon_stays_none_for_unknown_name(client, app):
    resp = client.post("/expenses/categories", data={
        "name": "全新自定义分类", "kind": "支出", "parent_id": "",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        cat = ExpenseCategory.query.filter_by(name="全新自定义分类", parent_id=None).one()
        assert cat.icon is None


def test_create_category_explicit_icon_not_overridden(client, app):
    resp = client.post("/expenses/categories", data={
        "name": "买买买买改", "kind": "支出", "parent_id": "", "icon": "🎯",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        cat = ExpenseCategory.query.filter_by(name="买买买买改", parent_id=None).one()
        assert cat.icon == "🎯"


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
