import datetime as dt
from decimal import Decimal
from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord
from app.services.expense_stats import monthly_stats, yearly_stats


def _cat(kind, name, parent=None):
    c = ExpenseCategory(kind=kind, name=name, parent_id=parent.id if parent else None)
    db.session.add(c)
    db.session.commit()
    return c


def _record(kind, date, category, amount, tag=None, source="import"):
    db.session.add(ExpenseRecord(kind=kind, date=date, category_id=category.id,
                                 tag_id=tag.id if tag else None, amount=Decimal(amount), source=source))
    db.session.commit()


def test_monthly_stats_totals_and_category_breakdown(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        shopping = _cat("支出", "买买买买")
        market = _cat("支出", "超市市场", shopping)
        salary = _cat("收入", "工资收入")
        market_tag = ExpenseTag(name="超市")
        db.session.add(market_tag)
        db.session.commit()

        _record("支出", dt.date(2025, 6, 1), lunch, "30.00")
        _record("支出", dt.date(2025, 6, 2), market, "50.00", tag=market_tag)
        _record("收入", dt.date(2025, 6, 5), salary, "8000.00")
        # 上月记录用于环比
        _record("支出", dt.date(2025, 5, 15), lunch, "40.00")

        s = monthly_stats(2025, 6)
        assert s["total_expense"] == Decimal("80.00")
        assert s["total_income"] == Decimal("8000.00")
        assert s["balance"] == Decimal("7920.00")
        assert s["mom"]["diff"] == Decimal("40.00")
        assert s["mom"]["pct"] == Decimal("100.00")

        cats = {c["category"]: c["total"] for c in s["by_category"]}
        assert cats == {"食品酒水": Decimal("30.00"), "买买买买": Decimal("50.00")}

        june_1 = next(d for d in s["daily"] if d["date"] == dt.date(2025, 6, 1))
        assert june_1["total"] == Decimal("30.00")
        assert len(s["daily"]) == 30

        assert s["tag_top"] == [{"tag": "超市", "total": Decimal("50.00")}]
        assert len(s["top_records"]) == 2


def test_monthly_stats_no_previous_month_has_no_pct(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        _record("支出", dt.date(2025, 1, 10), lunch, "20.00")
        s = monthly_stats(2025, 1)
        assert s["mom"]["pct"] is None
        assert s["mom"]["diff"] == Decimal("20.00")


def test_yearly_stats_monthly_series_and_yoy(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        _record("支出", dt.date(2024, 3, 1), lunch, "100.00")
        _record("支出", dt.date(2025, 3, 1), lunch, "150.00")
        _record("支出", dt.date(2025, 7, 1), lunch, "50.00")

        s = yearly_stats(2025)
        march = next(m for m in s["monthly"] if m["month"] == 3)
        assert march["expense"] == Decimal("150.00")
        july = next(m for m in s["monthly"] if m["month"] == 7)
        assert july["expense"] == Decimal("50.00")

        rank = s["category_rank"][0]
        assert rank["category"] == "食品酒水"
        assert rank["total"] == Decimal("200.00")
        assert rank["yoy"]["diff"] == Decimal("100.00")
        assert rank["yoy"]["pct"] == Decimal("100.00")

        assert s["total_expense"] == Decimal("200.00")
        assert s["days_with_expense"] == 2
        assert s["max_single"].amount == Decimal("150.00")


def test_yearly_stats_category_with_no_prior_year_has_no_yoy(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        _record("支出", dt.date(2025, 1, 1), lunch, "10.00")
        s = yearly_stats(2025)
        assert s["category_rank"][0]["yoy"] == {"diff": None, "pct": None}
