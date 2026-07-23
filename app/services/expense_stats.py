"""日常消费的月度/年度统计聚合层。所有金额均为人民币 Decimal，两位四舍五入。
纯查询，无 HTTP，供 blueprints/expenses.py 调用。设计见
docs/specs/2026-07-20-daily-expense-design.md。
"""
import calendar
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

from app.models.expense import ExpenseCategory, ExpenseRecord

TWO = Decimal("0.01")
ZERO = Decimal("0.00")


def _q(amount):
    return Decimal(amount).quantize(TWO, rounding=ROUND_HALF_UP)


def _mom(current, previous):
    """环比：{diff, pct}；上期为 0 或无数据时 pct 为 None。"""
    diff = _q(current - previous)
    pct = None
    if previous:
        pct = _q((current - previous) / previous * 100)
    return {"diff": diff, "pct": pct}


def _top_category(cat):
    """记录分类可能直接指一级；一级返回自身，二级返回其 parent。"""
    return cat if cat.parent_id is None else cat.parent


# ---- 月度/年度/总览三处共用的聚合小工具 ----
# 三个 stats 函数的查询范围各不相同（当月 / 循环 12 月 / 全量分桶），但「按分类归拢、
# 按标签归拢、算占比排行」这几步逻辑是一样的，抽到这里，改口径只改一处。

def _aggregate_by_top_category(records):
    """把支出记录按一级分类归拢：{一级id: {category, icon, total(未量化)}}。"""
    totals = {}
    for r in records:
        top = _top_category(r.category)
        entry = totals.setdefault(top.id, {"category": top.name, "icon": top.icon, "total": ZERO})
        entry["total"] += r.amount
    return totals


def _rank_categories(totals, total, prev_totals=None):
    """一级分类排行：按金额降序，附占比 pct。传了 prev_totals 则每行再附同比 yoy。
    total 是占比分母（各调用方按自己展示的支出合计传入）。"""
    rows = []
    for cid, entry in totals.items():
        row = {"category": entry["category"], "icon": entry["icon"], "total": _q(entry["total"])}
        if prev_totals is not None:
            prev = prev_totals.get(cid)
            row["yoy"] = _mom(entry["total"], prev["total"]) if prev else {"diff": None, "pct": None}
        rows.append(row)
    rows.sort(key=lambda e: e["total"], reverse=True)
    for row in rows:
        row["pct"] = _q(row["total"] / total * 100) if total else ZERO
    return rows


# 一级分类榜 / 二级分类榜 / 标签榜 三块共用：都是「按某维度归拢 → 金额降序 → 每项带单笔
# Top N」。归拢维度不同（一级 / 二级 / 标签），排行项的附加字段不同（占比 / 同比 / 笔数 /
# 所属一级），但单笔 Top N 这步一样，抽到 _top_records 一处维护。

def _top_records(records, limit):
    """取金额最高的前 limit 笔，序列化成榜项里的 records（Decimal / date 原样，序列化交蓝图）。"""
    recs = sorted(records, key=lambda r: r.amount, reverse=True)[:limit]
    return [{"date": r.date, "note": r.note, "category": r.category.name,
             "tag": r.tag.name if r.tag else None, "amount": _q(r.amount)} for r in recs]


def category_level1_board(records, total, record_limit=15, prev_totals=None):
    """一级分类榜：所有一级按金额降序 + 占 total 比（传 prev_totals 则附同比 yoy），
    每项带其名下（跨所有二级）单笔支出 Top N。前端渲染成两栏 Miller 列（左选一级、右看单笔）。"""
    groups = {}
    for r in records:
        top = _top_category(r.category)
        g = groups.setdefault(top.id, {"id": top.id, "name": top.name, "icon": top.icon,
                                       "total": ZERO, "records": []})
        g["total"] += r.amount
        g["records"].append(r)
    result = []
    for g in groups.values():
        node = {"name": g["name"], "icon": g["icon"], "total": _q(g["total"]),
                "pct": _q(g["total"] / total * 100) if total else ZERO,
                "records": _top_records(g["records"], record_limit)}
        if prev_totals is not None:
            prev = prev_totals.get(g["id"])
            node["yoy"] = _mom(g["total"], prev["total"]) if prev else {"diff": None, "pct": None}
        result.append(node)
    result.sort(key=lambda e: e["total"], reverse=True)
    return result


def category_level2_board(records, total, record_limit=15):
    """二级分类榜：所有真正的二级（跨一级全局）按金额降序 + 占 total 比，每项带其单笔支出
    Top N 及所属一级 parent。直接挂在一级、无二级的记录跳过。两栏 Miller 列。"""
    groups = {}
    for r in records:
        cat = r.category
        if cat.parent_id is None:
            continue
        g = groups.setdefault(cat.id, {"name": cat.name, "parent": cat.parent.name,
                                       "icon": cat.icon or cat.parent.icon, "total": ZERO, "records": []})
        g["total"] += r.amount
        g["records"].append(r)
    result = []
    for g in groups.values():
        result.append({"name": g["name"], "parent": g["parent"], "icon": g["icon"],
                       "total": _q(g["total"]), "pct": _q(g["total"] / total * 100) if total else ZERO,
                       "records": _top_records(g["records"], record_limit)})
    result.sort(key=lambda e: e["total"], reverse=True)
    return result


def tag_drilldown(records, record_limit=15):
    """标签榜：所有打了标签的支出按标签归拢，金额降序，每项带 {tag, total, count, records}。
    没打标签的记录跳过。两栏 Miller 列（左选标签、右看单笔）。"""
    groups = {}
    for r in records:
        if not r.tag:
            continue
        g = groups.setdefault(r.tag.name, {"tag": r.tag.name, "total": ZERO, "count": 0, "records": []})
        g["total"] += r.amount
        g["count"] += 1
        g["records"].append(r)
    result = [{"tag": g["tag"], "total": _q(g["total"]), "count": g["count"],
               "records": _top_records(g["records"], record_limit)} for g in groups.values()]
    result.sort(key=lambda e: e["total"], reverse=True)
    return result


def monthly_stats(year, month):
    start = dt.date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]
    end = dt.date(year, month, days_in_month)
    records = (ExpenseRecord.query
              .filter(ExpenseRecord.date >= start, ExpenseRecord.date <= end)
              .all())
    expenses = [r for r in records if r.kind == "支出"]
    incomes = [r for r in records if r.kind == "收入"]
    total_expense = _q(sum((r.amount for r in expenses), ZERO))
    total_income = _q(sum((r.amount for r in incomes), ZERO))

    prev_month_date = start - dt.timedelta(days=1)
    prev_total = (ExpenseRecord.query
                 .filter(ExpenseRecord.kind == "支出",
                         ExpenseRecord.date >= prev_month_date.replace(day=1),
                         ExpenseRecord.date <= prev_month_date)
                 .with_entities(ExpenseRecord.amount).all())
    prev_expense = _q(sum((a for (a,) in prev_total), ZERO))

    cat_list = _rank_categories(_aggregate_by_top_category(expenses), total_expense)
    cat1_board = category_level1_board(expenses, total_expense)
    cat2_board = category_level2_board(expenses, total_expense)

    daily = {start + dt.timedelta(days=i): ZERO for i in range(days_in_month)}
    for r in expenses:
        daily[r.date] += r.amount
    daily_list = [{"date": d, "total": _q(t)} for d, t in sorted(daily.items())]

    top_records = sorted(expenses, key=lambda r: r.amount, reverse=True)[:10]

    tag_drill = tag_drilldown(expenses)

    return {
        "year": year, "month": month,
        "total_expense": total_expense, "total_income": total_income,
        "balance": _q(total_income - total_expense),
        "mom": _mom(total_expense, prev_expense),
        "by_category": cat_list,
        "cat1_board": cat1_board,
        "cat2_board": cat2_board,
        "daily": daily_list,
        "top_records": top_records,
        "tag_drill": tag_drill,
    }


def _year_expense_records(year):
    """某年的全部支出记录。"""
    start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
    return (ExpenseRecord.query
            .filter(ExpenseRecord.kind == "支出",
                    ExpenseRecord.date >= start, ExpenseRecord.date <= end)
            .all())


def yearly_stats(year, today=None):
    today = today or dt.date.today()
    monthly = []
    for m in range(1, 13):
        start = dt.date(year, m, 1)
        end = dt.date(year, m, calendar.monthrange(year, m)[1])
        rows = (ExpenseRecord.query
               .filter(ExpenseRecord.date >= start, ExpenseRecord.date <= end)
               .with_entities(ExpenseRecord.kind, ExpenseRecord.amount).all())
        expense = _q(sum((a for k, a in rows if k == "支出"), ZERO))
        income = _q(sum((a for k, a in rows if k == "收入"), ZERO))
        monthly.append({"month": m, "expense": expense, "income": income})

    records = _year_expense_records(year)
    cur_totals = _aggregate_by_top_category(records)
    prev_totals = _aggregate_by_top_category(_year_expense_records(year - 1))
    total_expense = _q(sum((r.amount for r in records), ZERO))
    category_rank = _rank_categories(cur_totals, total_expense, prev_totals)
    cat1_board = category_level1_board(records, total_expense, prev_totals=prev_totals)
    cat2_board = category_level2_board(records, total_expense)
    tag_drill = tag_drilldown(records)

    total_income = _q(sum((a for row in monthly for a in (row["income"],)), ZERO))
    days_with_expense = len({r.date for r in records})
    max_single = max(records, key=lambda r: r.amount) if records else None

    prev_expense = _q(sum((e["total"] for e in prev_totals.values()), ZERO))
    expense_yoy = _mom(total_expense, prev_expense)

    # 均值口径按「已过去的时间」算，避免未过完的当年被 12 个月 / 365 天稀释
    if year < today.year:
        months_elapsed = 12
        days_elapsed = (dt.date(year, 12, 31) - dt.date(year, 1, 1)).days + 1  # 365/366
    elif year == today.year:
        months_elapsed = today.month
        days_elapsed = (today - dt.date(year, 1, 1)).days + 1
    else:  # 未来年份，无数据
        months_elapsed = days_elapsed = 0
    avg_month_expense = _q(total_expense / months_elapsed) if months_elapsed else ZERO
    avg_day_expense = _q(total_expense / days_elapsed) if days_elapsed else ZERO

    savings_rate = _q(_q(total_income - total_expense) / total_income * 100) if total_income else None

    months_with_expense = [m for m in monthly if m["expense"] > 0]
    top_month = max(months_with_expense, key=lambda m: m["expense"]) if months_with_expense else None
    low_month = min(months_with_expense, key=lambda m: m["expense"]) if months_with_expense else None

    return {
        "year": year,
        "monthly": monthly,
        "category_rank": category_rank,
        "cat1_board": cat1_board,
        "cat2_board": cat2_board,
        "tag_drill": tag_drill,
        "total_expense": total_expense,
        "total_income": total_income,
        "balance": _q(total_income - total_expense),
        "expense_yoy": expense_yoy,
        "savings_rate": savings_rate,
        "avg_month_expense": avg_month_expense,
        "avg_day_expense": avg_day_expense,
        "max_single": max_single,
        "days_with_expense": days_with_expense,
        "record_count": len(records),
        "top_month": top_month,
        "low_month": low_month,
    }


# 堆叠柱里单独上色的一级分类数量上限，超出的并入「其他」段，避免配色打架。
_STACK_TOP_N = 7


def overview_stats(today=None):
    """跨全部年份的整体统计（累计口径 + 逐年序列 + 分类逐年矩阵）。"""
    today = today or dt.date.today()
    records = ExpenseRecord.query.all()
    expenses = [r for r in records if r.kind == "支出"]
    incomes = [r for r in records if r.kind == "收入"]

    if not records:
        return {
            "years": [], "yearly": [], "category_rank": [], "cat1_board": [], "cat2_board": [],
            "tag_drill": [], "stack_cats": [], "cat_year_matrix": {},
            "total_expense": ZERO, "total_income": ZERO, "balance": ZERO,
            "avg_year_expense": ZERO, "avg_day_expense": ZERO, "savings_rate": None,
            "record_count": 0, "max_single": None, "top_year": None, "low_year": None,
            "first_date": None, "last_date": None,
        }

    total_expense = _q(sum((r.amount for r in expenses), ZERO))
    total_income = _q(sum((r.amount for r in incomes), ZERO))

    dates = [r.date for r in records]
    first_date, last_date = min(dates), max(dates)
    years = list(range(first_date.year, last_date.year + 1))

    exp_by_year = {y: ZERO for y in years}
    inc_by_year = {y: ZERO for y in years}
    for r in expenses:
        exp_by_year[r.date.year] += r.amount
    for r in incomes:
        inc_by_year[r.date.year] += r.amount

    yearly = []
    for i, y in enumerate(years):
        e = _q(exp_by_year[y])
        inc = _q(inc_by_year[y])
        prev_e = _q(exp_by_year[years[i - 1]]) if i > 0 else None
        yearly.append({
            "year": y, "expense": e, "income": inc, "balance": _q(inc - e),
            "savings_rate": _q((inc - e) / inc * 100) if inc else None,
            "yoy": _mom(e, prev_e) if prev_e is not None else {"diff": None, "pct": None},
        })

    # 一级分类全时段排行
    cat_totals = _aggregate_by_top_category(expenses)
    category_rank = _rank_categories(cat_totals, total_expense)
    cat1_board = category_level1_board(expenses, total_expense)
    cat2_board = category_level2_board(expenses, total_expense)

    # 分类 × 年份 堆叠矩阵：前 N 名单独成段，其余并入「其他」
    main_names = [c["category"] for c in category_rank[:_STACK_TOP_N]]
    has_other = len(category_rank) > _STACK_TOP_N
    stack_cats = list(main_names) + (["其他"] if has_other else [])
    matrix = {name: {y: ZERO for y in years} for name in stack_cats}
    id_to_stack = {cid: (e["category"] if e["category"] in main_names else "其他")
                   for cid, e in cat_totals.items()}
    for r in expenses:
        top = _top_category(r.category)
        matrix[id_to_stack[top.id]][r.date.year] += r.amount
    cat_year_matrix = {name: [_q(matrix[name][y]) for y in years] for name in stack_cats}

    # 标签全时段榜
    tag_drill = tag_drilldown(expenses)

    years_with_expense = [row for row in yearly if row["expense"] > 0]
    top_year = max(years_with_expense, key=lambda r: r["expense"]) if years_with_expense else None
    low_year = min(years_with_expense, key=lambda r: r["expense"]) if years_with_expense else None
    avg_year_expense = _q(total_expense / len(years_with_expense)) if years_with_expense else ZERO
    days_span = (last_date - first_date).days + 1
    avg_day_expense = _q(total_expense / days_span) if days_span else ZERO
    savings_rate = _q((total_income - total_expense) / total_income * 100) if total_income else None
    max_single = max(expenses, key=lambda r: r.amount) if expenses else None

    return {
        "years": years,
        "yearly": yearly,
        "category_rank": category_rank,
        "cat1_board": cat1_board,
        "cat2_board": cat2_board,
        "tag_drill": tag_drill,
        "stack_cats": stack_cats,
        "cat_year_matrix": cat_year_matrix,
        "total_expense": total_expense,
        "total_income": total_income,
        "balance": _q(total_income - total_expense),
        "avg_year_expense": avg_year_expense,
        "avg_day_expense": avg_day_expense,
        "savings_rate": savings_rate,
        "record_count": len(expenses),
        "max_single": max_single,
        "top_year": top_year,
        "low_year": low_year,
        "first_date": first_date,
        "last_date": last_date,
    }
