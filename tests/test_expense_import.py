import io
from decimal import Decimal
from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord
from app.services.expense_import import parse_rows, import_rows
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
