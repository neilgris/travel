import datetime as dt
from decimal import Decimal

from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord, ExpenseRule
from app.services.expense_recurring import due_dates, materialize, next_due, run_all


def _cat(kind, name, parent=None):
    c = ExpenseCategory(kind=kind, name=name, parent_id=parent.id if parent else None)
    db.session.add(c)
    db.session.commit()
    return c


def _rule(category, *, name="房租", amount="3500", interval=1,
          start=(2025, 1), end=None, tag=None, note=None, active=True):
    r = ExpenseRule(name=name, kind=category.kind, category_id=category.id,
                    tag_id=tag.id if tag else None, amount=Decimal(amount),
                    interval_months=interval, start_month=dt.date(start[0], start[1], 1),
                    end_month=dt.date(end[0], end[1], 1) if end else None,
                    note=note, active=active)
    db.session.add(r)
    db.session.commit()
    return r


# --- due_dates：只算「该记哪些天」，不碰数据库 ---

def test_due_dates_monthly_up_to_today(app):
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), interval=1, start=(2025, 1))
        assert due_dates(rule, dt.date(2025, 4, 15)) == [
            dt.date(2025, 1, 1), dt.date(2025, 2, 1),
            dt.date(2025, 3, 1), dt.date(2025, 4, 1),
        ]


def test_due_dates_every_three_months_keeps_start_month_phase(app):
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), interval=3, start=(2025, 2))
        assert due_dates(rule, dt.date(2025, 9, 20)) == [
            dt.date(2025, 2, 1), dt.date(2025, 5, 1), dt.date(2025, 8, 1),
        ]


def test_due_dates_yearly(app):
    with app.app_context():
        rule = _rule(_cat("支出", "保险"), interval=12, start=(2023, 6))
        assert due_dates(rule, dt.date(2026, 1, 1)) == [
            dt.date(2023, 6, 1), dt.date(2024, 6, 1), dt.date(2025, 6, 1),
        ]


def test_due_dates_stops_at_end_month_inclusive(app):
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), interval=1, start=(2025, 1), end=(2025, 3))
        assert due_dates(rule, dt.date(2025, 12, 31)) == [
            dt.date(2025, 1, 1), dt.date(2025, 2, 1), dt.date(2025, 3, 1),
        ]


def test_due_dates_empty_when_start_month_in_future(app):
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), interval=1, start=(2026, 5))
        assert due_dates(rule, dt.date(2026, 1, 10)) == []


def test_due_dates_includes_current_month_from_day_one(app):
    """今天是 3 月 1 号，本月这笔就该算进来。"""
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), interval=1, start=(2025, 3))
        assert due_dates(rule, dt.date(2025, 3, 1)) == [dt.date(2025, 3, 1)]


# --- next_due：列表里给用户看「下一笔什么时候」 ---

def test_next_due_steps_past_today(app):
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), interval=3, start=(2025, 2))
        assert next_due(rule, dt.date(2025, 9, 20)) == dt.date(2025, 11, 1)


def test_next_due_is_start_month_when_rule_not_started(app):
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), start=(2026, 5))
        assert next_due(rule, dt.date(2026, 1, 10)) == dt.date(2026, 5, 1)


def test_next_due_none_after_end_month(app):
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), start=(2025, 1), end=(2025, 3))
        assert next_due(rule, dt.date(2025, 6, 1)) is None


# --- materialize：把该记的写进库 ---

def test_materialize_creates_records_with_rule_fields(app):
    with app.app_context():
        cat = _cat("收入", "房租收入")
        tag = ExpenseTag(name="出租")
        db.session.add(tag)
        db.session.commit()
        rule = _rule(cat, name="房租收入", amount="5000", start=(2025, 1),
                     tag=tag, note="每月房租")

        created = materialize(rule, dt.date(2025, 3, 5))

        assert len(created) == 3
        rows = ExpenseRecord.query.order_by(ExpenseRecord.date).all()
        assert [r.date for r in rows] == [
            dt.date(2025, 1, 1), dt.date(2025, 2, 1), dt.date(2025, 3, 1)
        ]
        first = rows[0]
        assert first.kind == "收入"
        assert first.category_id == cat.id
        assert first.tag_id == tag.id
        assert first.amount == Decimal("5000")
        assert first.note == "每月房租"
        assert first.source == "auto"
        assert first.rule_id == rule.id


def test_materialize_is_idempotent(app):
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), start=(2025, 1))

        assert len(materialize(rule, dt.date(2025, 3, 5))) == 3
        assert materialize(rule, dt.date(2025, 3, 5)) == []
        assert ExpenseRecord.query.count() == 3


def test_materialize_fills_only_the_gap(app):
    """中间那条被手工删了，再跑只补回缺的一条。"""
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), start=(2025, 1))
        materialize(rule, dt.date(2025, 3, 5))

        february = ExpenseRecord.query.filter_by(date=dt.date(2025, 2, 1)).one()
        db.session.delete(february)
        db.session.commit()

        created = materialize(rule, dt.date(2025, 3, 5))
        assert [r.date for r in created] == [dt.date(2025, 2, 1)]
        assert ExpenseRecord.query.count() == 3


def test_materialize_extends_into_new_months_over_time(app):
    """应用隔了几个月才打开，一次补齐中间所有月份。"""
    with app.app_context():
        rule = _rule(_cat("支出", "房租"), start=(2025, 1))
        materialize(rule, dt.date(2025, 1, 20))

        created = materialize(rule, dt.date(2025, 5, 2))
        assert [r.date for r in created] == [
            dt.date(2025, 2, 1), dt.date(2025, 3, 1),
            dt.date(2025, 4, 1), dt.date(2025, 5, 1),
        ]


def test_materialize_ignores_manual_records_of_same_category(app):
    """规则只认自己名下的记录，手工记的那笔不影响它。"""
    with app.app_context():
        cat = _cat("支出", "房租")
        db.session.add(ExpenseRecord(kind="支出", date=dt.date(2025, 1, 1),
                                     category_id=cat.id, amount=Decimal("3500"),
                                     source="manual"))
        db.session.commit()
        rule = _rule(cat, start=(2025, 1))

        created = materialize(rule, dt.date(2025, 1, 15))
        assert len(created) == 1
        assert ExpenseRecord.query.count() == 2


# --- run_all：遍历所有启用的规则 ---

def test_run_all_skips_inactive_rules(app):
    with app.app_context():
        _rule(_cat("支出", "房租"), name="房租", start=(2025, 1), active=True)
        _rule(_cat("支出", "宽带"), name="宽带", start=(2025, 1), active=False)

        assert run_all(dt.date(2025, 2, 10)) == 2
        assert ExpenseRecord.query.count() == 2


def test_run_all_counts_across_rules_and_is_idempotent(app):
    with app.app_context():
        _rule(_cat("支出", "房租"), name="房租", start=(2025, 1))
        _rule(_cat("收入", "房租收入"), name="房租收入", start=(2025, 1))

        assert run_all(dt.date(2025, 3, 1)) == 6
        assert run_all(dt.date(2025, 3, 1)) == 0
