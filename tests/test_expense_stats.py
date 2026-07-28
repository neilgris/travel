import datetime as dt
from decimal import Decimal
from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord
from app.services.expense_stats import (monthly_stats, yearly_stats, overview_stats,
                                         trend_stats, trend_year_records)


def _cat(kind, name, parent=None, icon=None):
    c = ExpenseCategory(kind=kind, name=name, icon=icon, parent_id=parent.id if parent else None)
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

        assert [t["tag"] for t in s["tag_drill"]] == ["超市"]
        assert s["tag_drill"][0]["total"] == Decimal("50.00")
        assert s["tag_drill"][0]["count"] == 1
        assert len(s["top_records"]) == 2


def test_monthly_stats_no_previous_month_has_no_pct(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        _record("支出", dt.date(2025, 1, 10), lunch, "20.00")
        s = monthly_stats(2025, 1)
        assert s["mom"]["pct"] is None
        assert s["mom"]["diff"] == Decimal("20.00")


def test_category_level1_board_ranks_with_top_records(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        dinner = _cat("支出", "晚餐", food)
        shop = _cat("支出", "买买买买")
        _record("支出", dt.date(2025, 6, 1), lunch, "30.00")
        _record("支出", dt.date(2025, 6, 2), lunch, "80.00")
        _record("支出", dt.date(2025, 6, 3), dinner, "50.00")
        _record("支出", dt.date(2025, 6, 4), shop, "40.00")

        board = monthly_stats(2025, 6)["cat1_board"]
        # 一级：食品酒水 160 在前，买买买买 40 在后
        assert [c["name"] for c in board] == ["食品酒水", "买买买买"]
        assert board[0]["total"] == Decimal("160.00")
        assert board[0]["pct"] == Decimal("80.00")  # 160/200
        # 名下单笔跨其所有二级，按金额降序
        assert [r["amount"] for r in board[0]["records"]] == [Decimal("80.00"), Decimal("50.00"), Decimal("30.00")]


def test_category_level2_board_sorts_all_subcategories_globally(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        shop = _cat("支出", "买买买买")
        market = _cat("支出", "超市", shop)
        misc = _cat("支出", "其他杂项")  # 直接挂一级、无二级 → 不入二级榜
        _record("支出", dt.date(2025, 6, 1), lunch, "30.00")
        _record("支出", dt.date(2025, 6, 2), market, "70.00")
        _record("支出", dt.date(2025, 6, 3), lunch, "20.00")
        _record("支出", dt.date(2025, 6, 4), misc, "99.00")

        board = monthly_stats(2025, 6)["cat2_board"]
        assert [b["name"] for b in board] == ["超市", "午餐"]  # 70 > 50
        assert board[0]["parent"] == "买买买买"
        assert board[0]["total"] == Decimal("70.00")
        assert board[0]["pct"] == Decimal("31.96")  # 70/219（分母 = 全部支出，含未细分的 99）
        assert [r["amount"] for r in board[1]["records"]] == [Decimal("30.00"), Decimal("20.00")]


def test_tag_drilldown_ranks_all_tags_with_top_records(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        t_super = ExpenseTag(name="超市")
        t_coffee = ExpenseTag(name="咖啡")
        db.session.add_all([t_super, t_coffee])
        db.session.commit()
        _record("支出", dt.date(2025, 6, 1), lunch, "30.00", tag=t_super)
        _record("支出", dt.date(2025, 6, 2), lunch, "80.00", tag=t_super)
        _record("支出", dt.date(2025, 6, 3), lunch, "50.00", tag=t_coffee)
        _record("支出", dt.date(2025, 6, 4), lunch, "20.00")  # 无标签，跳过

        drill = monthly_stats(2025, 6)["tag_drill"]
        assert [t["tag"] for t in drill] == ["超市", "咖啡"]  # 110 > 50
        assert drill[0]["total"] == Decimal("110.00")
        assert drill[0]["count"] == 2
        assert [r["amount"] for r in drill[0]["records"]] == [Decimal("80.00"), Decimal("30.00")]


def test_yearly_category_level1_board_has_yoy(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        _record("支出", dt.date(2024, 3, 1), lunch, "100.00")
        _record("支出", dt.date(2025, 3, 1), lunch, "150.00")
        board = yearly_stats(2025)["cat1_board"]
        assert board[0]["yoy"]["pct"] == Decimal("50.00")  # (150-100)/100


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


def test_trend_stats_yearly_series_per_dimension(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        dinner = _cat("支出", "晚餐", food)
        salary = _cat("收入", "工资收入")
        trip_tag = ExpenseTag(name="旅行")
        db.session.add(trip_tag)
        db.session.commit()

        _record("支出", dt.date(2023, 3, 1), lunch, "30.00")
        _record("支出", dt.date(2024, 3, 1), lunch, "50.00", tag=trip_tag)
        _record("支出", dt.date(2025, 3, 1), dinner, "20.00")
        _record("收入", dt.date(2025, 1, 5), salary, "8000.00", tag=trip_tag)

        s = trend_stats()
        assert s["years"] == [2023, 2024, 2025]

        # 一级 食品酒水：午餐 + 晚餐 三年汇总
        food_dim = next(d for d in s["dimensions"] if d["type"] == "cat1" and d["name"] == "食品酒水")
        assert food_dim["kind"] == "支出"
        assert food_dim["amounts"] == [Decimal("30.00"), Decimal("50.00"), Decimal("20.00")]
        assert food_dim["counts"] == [1, 1, 1]
        assert food_dim["total"] == Decimal("100.00")

        # 二级 午餐：仅 2023 / 2024，2025 补 0
        lunch_dim = next(d for d in s["dimensions"] if d["type"] == "cat2" and d["name"] == "午餐")
        assert lunch_dim["parent"] == "食品酒水"
        assert lunch_dim["amounts"] == [Decimal("30.00"), Decimal("50.00"), Decimal("0.00")]

        # 收入一级
        salary_dim = next(d for d in s["dimensions"] if d["name"] == "工资收入")
        assert salary_dim["kind"] == "收入"
        assert salary_dim["type"] == "cat1"
        assert salary_dim["amounts"] == [Decimal("0.00"), Decimal("0.00"), Decimal("8000.00")]

        # 标签跨支出/收入汇总，kind 为 None
        tag_dim = next(d for d in s["dimensions"] if d["type"] == "tag" and d["name"] == "旅行")
        assert tag_dim["kind"] is None
        assert tag_dim["amounts"] == [Decimal("0.00"), Decimal("50.00"), Decimal("8000.00")]
        assert tag_dim["counts"] == [0, 1, 1]

        # 默认选中全局金额最高维度 = 标签「旅行」（8050 > 工资收入 8000）
        assert s["default_key"] == tag_dim["key"]

        # 二级维度带 parent_key，供联动选择器把二级挂回一级
        assert lunch_dim["parent_key"] == food_dim["key"]


def test_trend_stats_tag_grouped_by_dominant_top_category(app):
    """标签维度带 group（花得最多的那个一级分类）+ group_icon，走势页左栏按它给标签分组。"""
    with app.app_context():
        food = _cat("支出", "食品酒水", icon="🍜")
        shopping = _cat("支出", "买买买买", icon="🛍️")
        sichuan = ExpenseTag(name="川菜")
        clothes = ExpenseTag(name="衣服鞋包")
        db.session.add_all([sichuan, clothes])
        db.session.commit()

        # 川菜：食品 300 / 购物 100 → 归到食品酒水（不是非此即彼，按金额多的那边）
        _record("支出", dt.date(2025, 3, 1), food, "300.00", tag=sichuan)
        _record("支出", dt.date(2025, 4, 1), shopping, "100.00", tag=sichuan)
        _record("支出", dt.date(2025, 5, 1), shopping, "900.00", tag=clothes)

        dims = {d["name"]: d for d in trend_stats()["dimensions"] if d["type"] == "tag"}
        assert dims["川菜"]["group"] == "食品酒水"
        assert dims["川菜"]["group_icon"] == "🍜"
        assert dims["衣服鞋包"]["group"] == "买买买买"

        # 标签整体排序：先按所属组的合计降序，再按标签自身金额降序
        tags = [d["name"] for d in trend_stats()["dimensions"] if d["type"] == "tag"]
        assert tags == ["衣服鞋包", "川菜"]  # 买买买买组 1000 > 食品酒水组 400


def test_trend_stats_tag_subgroup_from_tag_group_name(app):
    """标签组（菜系/火锅…）来自手工设的 group_name，作为一级分类下的第二层；
    未设分组的标签 subgroup 为 None，直接挂在一级分类下并排在有分组的后面。"""
    with app.app_context():
        food = _cat("支出", "食品酒水", icon="🍜")
        sichuan = ExpenseTag(name="川菜", group_name="中餐菜系")
        hotpot = ExpenseTag(name="四川火锅", group_name="火锅")
        canteen = ExpenseTag(name="食堂")  # 未分组
        db.session.add_all([sichuan, hotpot, canteen])
        db.session.commit()

        _record("支出", dt.date(2025, 3, 1), food, "100.00", tag=sichuan)
        _record("支出", dt.date(2025, 3, 2), food, "500.00", tag=hotpot)
        _record("支出", dt.date(2025, 3, 3), food, "900.00", tag=canteen)

        dims = {d["name"]: d for d in trend_stats()["dimensions"] if d["type"] == "tag"}
        assert dims["川菜"]["group"] == "食品酒水"      # 一级分类仍按金额推
        assert dims["川菜"]["subgroup"] == "中餐菜系"   # 标签组来自 group_name
        assert dims["四川火锅"]["subgroup"] == "火锅"
        assert dims["食堂"]["subgroup"] is None

        # 组内排序：有分组的按组合计降序在前，未分组的（哪怕金额最大）排最后
        tags = [d["name"] for d in trend_stats()["dimensions"] if d["type"] == "tag"]
        assert tags == ["四川火锅", "川菜", "食堂"]


def test_seed_tag_groups_fills_only_once(app):
    """预填只兜首次：已有任一标签设过组就整体跳过，不覆盖手工结果。"""
    from app.models.expense import seed_tag_groups
    with app.app_context():
        db.session.add_all([ExpenseTag(name="粤菜"), ExpenseTag(name="北京火锅"),
                            ExpenseTag(name="咖啡"), ExpenseTag(name="山姆")])
        db.session.commit()

        seed_tag_groups()
        got = {t.name: t.group_name for t in ExpenseTag.query.all()}
        assert got == {"粤菜": "中餐菜系", "北京火锅": "火锅", "咖啡": "甜品饮品", "山姆": None}

        # 手工改一个之后再跑，不应被覆盖回猜测值
        ExpenseTag.query.filter_by(name="咖啡").one().group_name = "酒水"
        db.session.commit()
        seed_tag_groups()
        assert ExpenseTag.query.filter_by(name="咖啡").one().group_name == "酒水"


def test_trend_stats_empty(app):
    with app.app_context():
        assert trend_stats() == {"years": [], "dimensions": [], "default_key": None}


def test_trend_year_records_by_dimension_and_year(app):
    with app.app_context():
        food = _cat("支出", "食品酒水")
        lunch = _cat("支出", "午餐", food)
        dinner = _cat("支出", "晚餐", food)
        trip_tag = ExpenseTag(name="旅行")
        db.session.add(trip_tag)
        db.session.commit()

        _record("支出", dt.date(2025, 3, 1), lunch, "30.00", tag=trip_tag)
        _record("支出", dt.date(2025, 4, 1), dinner, "80.00")
        _record("支出", dt.date(2024, 3, 1), lunch, "999.00")  # 别的年份不算

        # 一级：含全部二级，当年金额降序
        cat1 = trend_year_records(f"cat1-{food.id}", 2025)
        assert [r["amount"] for r in cat1] == [Decimal("80.00"), Decimal("30.00")]

        # 二级：只该二级
        cat2 = trend_year_records(f"cat2-{lunch.id}", 2025)
        assert [r["amount"] for r in cat2] == [Decimal("30.00")]

        # 标签
        tag = trend_year_records(f"tag-{trip_tag.id}", 2025)
        assert [r["amount"] for r in tag] == [Decimal("30.00")]

        # 上限截断
        assert trend_year_records(f"cat1-{food.id}", 2025, limit=1)[0]["amount"] == Decimal("80.00")

        # 未知前缀 / 无数据年 → 空
        assert trend_year_records("bogus-1", 2025) == []
        assert trend_year_records(f"cat1-{food.id}", 2099) == []
