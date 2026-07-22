import datetime as dt
from decimal import Decimal
from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord
from app.services.expense_stats import monthly_stats, yearly_stats, overview_stats


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


def test_yearly_stats_current_year_averages_use_elapsed_period(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        _record("支出", dt.date(2026, 1, 15), food, "300.00")
        _record("支出", dt.date(2026, 3, 10), food, "300.00")
        # 假装今天是 2026-04-10：已过 4 个月、第 100 天
        s = yearly_stats(2026, today=dt.date(2026, 4, 10))
        assert s["total_expense"] == Decimal("600.00")
        assert s["avg_month_expense"] == Decimal("150.00")  # 600 / 4
        day_of_year = (dt.date(2026, 4, 10) - dt.date(2026, 1, 1)).days + 1  # 100
        assert s["avg_day_expense"] == (Decimal("600.00") / day_of_year).quantize(Decimal("0.01"))


def test_yearly_stats_complete_year_averages_use_full_period_with_leap(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        _record("支出", dt.date(2024, 6, 1), food, "1200.00")
        s = yearly_stats(2024, today=dt.date(2026, 7, 21))
        assert s["avg_month_expense"] == Decimal("100.00")  # 1200 / 12
        # 2024 是闰年 → 366 天
        assert s["avg_day_expense"] == (Decimal("1200.00") / 366).quantize(Decimal("0.01"))


def test_yearly_stats_expense_yoy_savings_and_record_count(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        salary = _cat("收入", "工资")
        _record("支出", dt.date(2024, 5, 1), food, "100.00")
        _record("支出", dt.date(2025, 5, 1), food, "150.00")
        _record("支出", dt.date(2025, 8, 1), food, "50.00")
        _record("收入", dt.date(2025, 1, 1), salary, "1000.00")
        s = yearly_stats(2025, today=dt.date(2026, 7, 21))
        assert s["total_expense"] == Decimal("200.00")
        assert s["expense_yoy"]["diff"] == Decimal("100.00")  # 200 - 100
        assert s["expense_yoy"]["pct"] == Decimal("100.00")
        assert s["record_count"] == 2  # 仅 2025 的支出笔数
        # 结余率 = (1000 - 200) / 1000 * 100 = 80
        assert s["savings_rate"] == Decimal("80.00")


def test_yearly_stats_top_and_low_month_ignore_empty_months(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        _record("支出", dt.date(2025, 2, 1), food, "500.00")
        _record("支出", dt.date(2025, 6, 1), food, "100.00")
        s = yearly_stats(2025, today=dt.date(2026, 7, 21))
        assert s["top_month"]["month"] == 2
        assert s["top_month"]["expense"] == Decimal("500.00")
        # 最低月只在「有支出的月份」里取，不能选到 0 的空月
        assert s["low_month"]["month"] == 6
        assert s["low_month"]["expense"] == Decimal("100.00")


def test_yearly_stats_category_pct(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        shop = _cat("支出", "购物")
        _record("支出", dt.date(2025, 1, 1), food, "750.00")
        _record("支出", dt.date(2025, 1, 1), shop, "250.00")
        s = yearly_stats(2025, today=dt.date(2026, 7, 21))
        assert s["category_rank"][0]["pct"] == Decimal("75.00")
        assert s["category_rank"][1]["pct"] == Decimal("25.00")


def test_yearly_stats_empty_year_is_safe(app):
    with app.app_context():
        s = yearly_stats(2025, today=dt.date(2026, 7, 21))
        assert s["total_expense"] == Decimal("0.00")
        assert s["top_month"] is None
        assert s["low_month"] is None
        assert s["savings_rate"] is None
        assert s["record_count"] == 0
        assert s["expense_yoy"]["diff"] == Decimal("0.00")
        assert s["avg_day_expense"] == Decimal("0.00")


def test_overview_stats_totals_and_yearly_series(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        salary = _cat("收入", "工资")
        _record("支出", dt.date(2023, 5, 1), food, "100.00")
        _record("支出", dt.date(2024, 5, 1), food, "300.00")
        _record("支出", dt.date(2024, 8, 1), food, "100.00")
        _record("收入", dt.date(2024, 1, 1), salary, "1000.00")
        s = overview_stats(today=dt.date(2026, 7, 21))
        assert s["total_expense"] == Decimal("500.00")
        assert s["total_income"] == Decimal("1000.00")
        assert s["balance"] == Decimal("500.00")
        # 年份区间按首末记录推导，连续填满
        assert s["years"] == [2023, 2024]
        y2023 = next(r for r in s["yearly"] if r["year"] == 2023)
        y2024 = next(r for r in s["yearly"] if r["year"] == 2024)
        assert y2023["expense"] == Decimal("100.00")
        assert y2024["expense"] == Decimal("400.00")
        assert y2024["income"] == Decimal("1000.00")
        assert y2024["balance"] == Decimal("600.00")
        # 逐年同比
        assert y2024["yoy"]["pct"] == Decimal("300.00")  # (400-100)/100
        assert y2023["yoy"]["pct"] is None  # 首年无上一年


def test_overview_stats_averages_and_savings(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        salary = _cat("收入", "工资")
        _record("支出", dt.date(2023, 1, 1), food, "400.00")
        _record("支出", dt.date(2024, 1, 1), food, "600.00")
        _record("收入", dt.date(2024, 1, 1), salary, "2000.00")
        s = overview_stats(today=dt.date(2026, 7, 21))
        # 有支出的年数 = 2 → 年均 = 1000/2
        assert s["avg_year_expense"] == Decimal("500.00")
        # 结余率 = (2000-1000)/2000*100
        assert s["savings_rate"] == Decimal("50.00")
        assert s["record_count"] == 2  # 支出笔数


def test_overview_stats_category_rank_and_stacked_matrix(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        shop = _cat("支出", "购物")
        _record("支出", dt.date(2023, 1, 1), food, "300.00")
        _record("支出", dt.date(2024, 1, 1), food, "100.00")
        _record("支出", dt.date(2024, 1, 1), shop, "600.00")
        s = overview_stats(today=dt.date(2026, 7, 21))
        # 全时段排行：购物 700? no — food=400, shop=600 → shop first
        assert s["category_rank"][0]["category"] == "购物"
        assert s["category_rank"][0]["total"] == Decimal("600.00")
        assert s["category_rank"][0]["pct"] == Decimal("60.00")  # 600/1000
        # 堆叠矩阵：分类 × 年份
        assert set(s["stack_cats"]) == {"食品酒水", "购物"}
        food_series = dict(zip(s["years"], s["cat_year_matrix"]["食品酒水"]))
        assert food_series[2023] == Decimal("300.00")
        assert food_series[2024] == Decimal("100.00")
        shop_series = dict(zip(s["years"], s["cat_year_matrix"]["购物"]))
        assert shop_series[2023] == Decimal("0.00")
        assert shop_series[2024] == Decimal("600.00")


def test_overview_stats_buckets_small_categories_into_other(app):
    with app.app_context():
        # 建 9 个一级分类，超过 TOP 7 → 剩下归入「其他」
        cats = [_cat("支出", f"类{i}") for i in range(9)]
        for i, c in enumerate(cats):
            _record("支出", dt.date(2024, 1, 1), c, str((i + 1) * 100))
        s = overview_stats(today=dt.date(2026, 7, 21))
        assert "其他" in s["stack_cats"]
        # 堆叠段数 = 7 主分类 + 1 其他
        assert len(s["stack_cats"]) == 8
        # 每个分类在每一年都有一个数（含 0），长度对齐年份数
        for name in s["stack_cats"]:
            assert len(s["cat_year_matrix"][name]) == len(s["years"])


def test_overview_stats_top_and_low_year(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        _record("支出", dt.date(2023, 1, 1), food, "800.00")
        _record("支出", dt.date(2024, 1, 1), food, "200.00")
        s = overview_stats(today=dt.date(2026, 7, 21))
        assert s["top_year"]["year"] == 2023
        assert s["low_year"]["year"] == 2024
        assert s["max_single"].amount == Decimal("800.00")


def test_overview_stats_empty_is_safe(app):
    with app.app_context():
        s = overview_stats(today=dt.date(2026, 7, 21))
        assert s["total_expense"] == Decimal("0.00")
        assert s["years"] == []
        assert s["yearly"] == []
        assert s["category_rank"] == []
        assert s["stack_cats"] == []
        assert s["top_year"] is None
        assert s["low_year"] is None
        assert s["max_single"] is None
        assert s["savings_rate"] is None
        assert s["avg_year_expense"] == Decimal("0.00")
        assert s["record_count"] == 0
