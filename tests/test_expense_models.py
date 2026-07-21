import pytest
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord, seed_default_categories
import datetime as dt
from decimal import Decimal


def test_seed_default_categories_creates_tree(session):
    seed_default_categories()
    food = ExpenseCategory.query.filter_by(name="食品酒水", parent_id=None).one()
    assert food.kind == "支出"
    names = {c.name for c in food.children}
    assert "午餐" in names
    income = ExpenseCategory.query.filter_by(name="职业收入", parent_id=None).one()
    assert income.kind == "收入"


def test_seed_is_idempotent(session):
    seed_default_categories()
    count_before = ExpenseCategory.query.count()
    seed_default_categories()
    assert ExpenseCategory.query.count() == count_before


def test_duplicate_category_name_under_same_parent_rejected(session):
    top = ExpenseCategory(name="食品酒水", kind="支出")
    db.session.add(top)
    db.session.commit()
    db.session.add(ExpenseCategory(name="午餐", kind="支出", parent_id=top.id))
    db.session.commit()
    db.session.add(ExpenseCategory(name="午餐", kind="支出", parent_id=top.id))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_same_name_allowed_under_different_parents(session):
    top1 = ExpenseCategory(name="其他杂项", kind="支出")
    top2 = ExpenseCategory(name="金融保险", kind="支出")
    db.session.add_all([top1, top2])
    db.session.commit()
    db.session.add(ExpenseCategory(name="其他支出", kind="支出", parent_id=top1.id))
    db.session.add(ExpenseCategory(name="其他支出", kind="支出", parent_id=top2.id))
    db.session.commit()
    assert ExpenseCategory.query.filter_by(name="其他支出").count() == 2


def test_tag_name_unique(session):
    db.session.add(ExpenseTag(name="超市"))
    db.session.commit()
    db.session.add(ExpenseTag(name="超市"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_record_fingerprint_unique(session):
    top = ExpenseCategory(name="食品酒水", kind="支出")
    db.session.add(top)
    db.session.commit()
    sub = ExpenseCategory(name="午餐", kind="支出", parent_id=top.id)
    db.session.add(sub)
    db.session.commit()
    r1 = ExpenseRecord(kind="支出", date=dt.date(2025, 1, 1), category_id=sub.id,
                       amount=Decimal("10.00"), source="import", fingerprint="abc")
    db.session.add(r1)
    db.session.commit()
    r2 = ExpenseRecord(kind="支出", date=dt.date(2025, 1, 2), category_id=sub.id,
                       amount=Decimal("20.00"), source="import", fingerprint="abc")
    db.session.add(r2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_manual_records_allow_multiple_null_fingerprints(session):
    top = ExpenseCategory(name="食品酒水", kind="支出")
    db.session.add(top)
    db.session.commit()
    sub = ExpenseCategory(name="午餐", kind="支出", parent_id=top.id)
    db.session.add(sub)
    db.session.commit()
    db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 1, 1), category_id=sub.id,
                                 amount=Decimal("10.00"), source="manual"))
    db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 1, 2), category_id=sub.id,
                                 amount=Decimal("20.00"), source="manual"))
    db.session.commit()
    assert ExpenseRecord.query.count() == 2
