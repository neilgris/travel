import io
import datetime as dt
from decimal import Decimal
from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord
from app.services.expense_import import parse_rows, import_rows, refresh_all_fingerprints
from tests.expense_xls_helper import make_expense_xls_bytes


def test_parse_rows_reads_both_sheets():
    content = make_expense_xls_bytes(
        expense_rows=[{"date": "2025-12-31 15:51:51", "cat1": "买买买买", "cat2": "超市市场",
                       "amount": 200.7, "merchant": "超市", "note": "山姆"}],
        income_rows=[{"date": "2025-01-05 09:00:00", "cat1": "职业收入", "cat2": "工资收入",
                     "amount": 8000, "note": ""}],
    )
    rows = parse_rows(io.BytesIO(content))
    assert len(rows) == 2
    expense = next(r for r in rows if r["kind"] == "支出")
    assert expense["date"].isoformat() == "2025-12-31"
    assert expense["cat1"] == "买买买买"
    assert expense["cat2"] == "超市市场"
    assert expense["amount"] == Decimal("200.7")
    assert expense["tag"] == "超市"
    assert expense["note"] == "山姆"
    income = next(r for r in rows if r["kind"] == "收入")
    assert income["cat1"] == "职业收入"


def test_import_rows_creates_categories_and_tags(app):
    with app.app_context():
        content = make_expense_xls_bytes(expense_rows=[
            {"date": "2025-12-31 15:51:51", "cat1": "买买买买", "cat2": "超市市场",
             "amount": 200.7, "merchant": "超市", "note": "山姆"},
        ])
        result = import_rows(parse_rows(io.BytesIO(content)))
        assert result == {"created": 1, "skipped": 0, "new_categories": 2, "new_tags": 1}
        record = ExpenseRecord.query.one()
        assert record.amount == Decimal("200.70")
        assert record.category.name == "超市市场"
        assert record.category.parent.name == "买买买买"
        assert record.tag.name == "超市"
        assert record.source == "import"


def test_import_rows_assigns_known_icon_to_new_categories(app):
    with app.app_context():
        content = make_expense_xls_bytes(expense_rows=[
            {"date": "2025-12-31 15:51:51", "cat1": "买买买买", "cat2": "超市市场",
             "amount": 200.7, "merchant": "超市", "note": "山姆"},
        ])
        import_rows(parse_rows(io.BytesIO(content)))
        record = ExpenseRecord.query.one()
        assert record.category.icon == "🛒"
        assert record.category.parent.icon == "🛍️"


def test_import_rows_leaves_icon_none_for_unknown_category_name(app):
    with app.app_context():
        content = make_expense_xls_bytes(expense_rows=[
            {"date": "2025-12-31 15:51:51", "cat1": "临时测试分类", "cat2": "",
             "amount": 10.0, "merchant": "", "note": ""},
        ])
        import_rows(parse_rows(io.BytesIO(content)))
        record = ExpenseRecord.query.one()
        assert record.category.icon is None


def test_import_rows_without_merchant_leaves_tag_null(app):
    with app.app_context():
        content = make_expense_xls_bytes(expense_rows=[
            {"date": "2025-01-01 10:00:00", "cat1": "行车交通", "cat2": "私家车费用",
             "amount": 4.0, "merchant": "", "note": "北投停车"},
        ])
        import_rows(parse_rows(io.BytesIO(content)))
        record = ExpenseRecord.query.one()
        assert record.tag_id is None


def test_reimporting_same_file_skips_everything(app):
    with app.app_context():
        content = make_expense_xls_bytes(expense_rows=[
            {"date": "2025-12-31 15:51:51", "cat1": "买买买买", "cat2": "超市市场",
             "amount": 200.7, "merchant": "超市", "note": "山姆"},
            {"date": "2025-12-31 15:51:10", "cat1": "买买买买", "cat2": "商场",
             "amount": 79.0, "merchant": "超市", "note": "muji"},
        ])
        first = import_rows(parse_rows(io.BytesIO(content)))
        assert first["created"] == 2
        second = import_rows(parse_rows(io.BytesIO(content)))
        assert second == {"created": 0, "skipped": 2, "new_categories": 0, "new_tags": 0}
        assert ExpenseRecord.query.count() == 2


def test_duplicate_rows_within_same_file_both_kept(app):
    """同一天同金额同备注的两笔真实消费（同键序号区分），不应互相当成重复而丢失。"""
    with app.app_context():
        content = make_expense_xls_bytes(expense_rows=[
            {"date": "2025-06-01 08:00:00", "cat1": "行车交通", "cat2": "私家车费用",
             "amount": 10.0, "merchant": "充电", "note": "小区"},
            {"date": "2025-06-01 20:00:00", "cat1": "行车交通", "cat2": "私家车费用",
             "amount": 10.0, "merchant": "充电", "note": "小区"},
        ])
        result = import_rows(parse_rows(io.BytesIO(content)))
        assert result["created"] == 2
        assert ExpenseRecord.query.count() == 2


def test_import_does_not_touch_manual_records(app):
    with app.app_context():
        top = ExpenseCategory(name="食品酒水", kind="支出")
        db.session.add(top)
        db.session.commit()
        sub = ExpenseCategory(name="午餐", kind="支出", parent_id=top.id)
        db.session.add(sub)
        db.session.commit()
        db.session.add(ExpenseRecord(kind="支出", date=__import__("datetime").date(2025, 1, 1),
                                     category_id=sub.id, amount=Decimal("30.00"), source="manual"))
        db.session.commit()
        content = make_expense_xls_bytes(expense_rows=[
            {"date": "2025-01-01 12:00:00", "cat1": "食品酒水", "cat2": "午餐",
             "amount": 30.0, "note": ""},
        ])
        result = import_rows(parse_rows(io.BytesIO(content)))
        assert result["created"] == 1
        assert ExpenseRecord.query.count() == 2


# ---- 指纹口径一致性：所有算指纹的入口（导入 / 手工增改 / 批量改 / 重刷）必须同口径 ----
# 只要有一处口径不同，同一条记录换个入口写进去的指纹就跟导入算出来的对不上：
# 重刷指纹会白白报"有更新"，更要命的是再导一次同一份账单会认不出来、重复插入。

def _seed_food_lunch():
    top = ExpenseCategory(name="食品酒水", kind="支出")
    db.session.add(top)
    db.session.commit()
    sub = ExpenseCategory(name="午餐", kind="支出", parent_id=top.id)
    db.session.add(sub)
    db.session.commit()
    return top, sub


def test_manual_create_fingerprint_survives_refresh(client, app):
    """手工新增一条后立刻重刷指纹，不该有任何变化。"""
    with app.app_context():
        _, sub = _seed_food_lunch()
        sub_id = sub.id
    client.post("/expenses/new", data={
        "kind": "支出", "date": "2025-06-01", "category_id": str(sub_id),
        "amount": "35.50", "tag_name": "快餐", "note": "麦当劳",
    })
    with app.app_context():
        assert refresh_all_fingerprints()["changed"] == 0


def test_bulk_edit_fingerprint_survives_refresh(client, app):
    """批量改分类/标签后立刻重刷指纹，不该有任何变化。"""
    with app.app_context():
        top, sub = _seed_food_lunch()
        dinner = ExpenseCategory(name="晚餐", kind="支出", parent_id=top.id)
        db.session.add(dinner)
        db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=sub.id,
                                     amount=Decimal("35.50"), source="manual"))
        db.session.commit()
        dinner_id = dinner.id
    client.post("/expenses/bulk-edit", data={"field": "category", "value": str(dinner_id), "year": ""})
    with app.app_context():
        assert refresh_all_fingerprints()["changed"] == 0


def test_manual_record_fingerprint_matches_import_of_same_row(app):
    """手工记的一笔，跟从账单导入同样内容的一笔，指纹必须相同——
    这样再导一次含这笔的账单时能认出来是同一条，不会重复插入。"""
    with app.app_context():
        _, sub = _seed_food_lunch()
        manual = ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=sub.id,
                               amount=Decimal("35.50"), source="manual")
        db.session.add(manual)
        db.session.commit()
        refresh_all_fingerprints()  # 手工记录的指纹按统一口径补上
        manual_fp = db.session.get(ExpenseRecord, manual.id).fingerprint

        rows = parse_rows(io.BytesIO(make_expense_xls_bytes(expense_rows=[
            {"date": "2025-06-01 12:00:00", "cat1": "食品酒水", "cat2": "午餐",
             "amount": 35.5, "note": ""},
        ])))
        assert rows[0]["fingerprint"] == manual_fp


def test_refresh_is_idempotent(app):
    """连刷两次，第二次必须 0 变更。"""
    with app.app_context():
        _, sub = _seed_food_lunch()
        for amount in ("35.50", "12.00", "7.80"):
            db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=sub.id,
                                         amount=Decimal(amount), source="manual"))
        db.session.commit()
        refresh_all_fingerprints()
        assert refresh_all_fingerprints()["changed"] == 0


def test_refresh_repairs_gap_left_by_deleting_one_of_a_duplicate_pair(app):
    """同自然键的两条删掉一条后，幸存的那条要落回 seq=0——
    否则再导入这份账单时算出来的是 seq=0 的指纹，对不上，会重复插入。"""
    with app.app_context():
        _, sub = _seed_food_lunch()
        first, second = (ExpenseRecord(kind="支出", date=dt.date(2025, 6, 1), category_id=sub.id,
                                       amount=Decimal("35.50"), source="import") for _ in range(2))
        db.session.add_all([first, second])
        db.session.commit()
        refresh_all_fingerprints()
        db.session.delete(first)
        db.session.commit()
        refresh_all_fingerprints()

        rows = parse_rows(io.BytesIO(make_expense_xls_bytes(expense_rows=[
            {"date": "2025-06-01 12:00:00", "cat1": "食品酒水", "cat2": "午餐",
             "amount": 35.5, "note": ""},
        ])))
        assert import_rows(rows) == {"created": 0, "skipped": 1, "new_categories": 0, "new_tags": 0}


def test_delete_compacts_fingerprint_gap(client, app):
    """删掉同款两条中的第一条后，幸存那条要落回 seq=0，不留空洞——
    否则以后导入只含这笔一次的账单时算出的是空着的 seq=0，认不出来又插一条。
    「删除自己维护好不变量」的判据：删完立刻重刷，零变更。"""
    with app.app_context():
        _seed_food_lunch()
    content = make_expense_xls_bytes(expense_rows=[
        {"date": "2025-06-01 12:00:00", "cat1": "食品酒水", "cat2": "午餐", "amount": 35.5, "note": "同款"},
        {"date": "2025-06-01 12:00:00", "cat1": "食品酒水", "cat2": "午餐", "amount": 35.5, "note": "同款"},
    ])
    with app.app_context():
        assert import_rows(parse_rows(io.BytesIO(content)))["created"] == 2
        first_id = ExpenseRecord.query.order_by(ExpenseRecord.id).first().id

    client.post(f"/expenses/{first_id}/delete")

    with app.app_context():
        assert refresh_all_fingerprints()["changed"] == 0
        # 再导一份只含这笔一次的账单，应当认出来、跳过，而不是又插一条
        single = make_expense_xls_bytes(expense_rows=[
            {"date": "2025-06-01 12:00:00", "cat1": "食品酒水", "cat2": "午餐", "amount": 35.5, "note": "同款"},
        ])
        assert import_rows(parse_rows(io.BytesIO(single)))["created"] == 0
        assert ExpenseRecord.query.count() == 1
