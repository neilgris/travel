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

    by_category = {}
    for r in expenses:
        top = _top_category(r.category)
        entry = by_category.setdefault(top.id, {"category": top.name, "icon": top.icon, "total": ZERO})
        entry["total"] += r.amount
    cat_list = sorted(by_category.values(), key=lambda e: e["total"], reverse=True)
    for e in cat_list:
        e["total"] = _q(e["total"])
        e["pct"] = _q(e["total"] / total_expense * 100) if total_expense else ZERO

    daily = {start + dt.timedelta(days=i): ZERO for i in range(days_in_month)}
    for r in expenses:
        daily[r.date] += r.amount
    daily_list = [{"date": d, "total": _q(t)} for d, t in sorted(daily.items())]

    top_records = sorted(expenses, key=lambda r: r.amount, reverse=True)[:10]

    tag_totals = {}
    for r in expenses:
        if not r.tag:
            continue
        entry = tag_totals.setdefault(r.tag.name, ZERO)
        tag_totals[r.tag.name] = entry + r.amount
    tag_top = sorted(({"tag": k, "total": _q(v)} for k, v in tag_totals.items()),
                     key=lambda e: e["total"], reverse=True)[:10]

    return {
        "year": year, "month": month,
        "total_expense": total_expense, "total_income": total_income,
        "balance": _q(total_income - total_expense),
        "mom": _mom(total_expense, prev_expense),
        "by_category": cat_list,
        "daily": daily_list,
        "top_records": top_records,
        "tag_top": tag_top,
    }


def _year_category_totals(year):
    """{一级分类id: {"category":名, "icon":.., "total":Decimal}}，仅支出。"""
    start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
    records = (ExpenseRecord.query
              .filter(ExpenseRecord.kind == "支出",
                      ExpenseRecord.date >= start, ExpenseRecord.date <= end)
              .all())
    totals = {}
    for r in records:
        top = _top_category(r.category)
        entry = totals.setdefault(top.id, {"category": top.name, "icon": top.icon, "total": ZERO})
        entry["total"] += r.amount
    return totals, records


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

    cur_totals, records = _year_category_totals(year)
    prev_totals, _ = _year_category_totals(year - 1)
    category_rank = []
    for cid, entry in cur_totals.items():
        prev = prev_totals.get(cid)
        prev_total = prev["total"] if prev else ZERO
        row = dict(entry, total=_q(entry["total"]))
        row["yoy"] = _mom(entry["total"], prev_total) if prev else {"diff": None, "pct": None}
        category_rank.append(row)
    category_rank.sort(key=lambda e: e["total"], reverse=True)
    year_expense = sum((e["total"] for e in category_rank), ZERO)
    for row in category_rank:
        row["pct"] = _q(row["total"] / year_expense * 100) if year_expense else ZERO

    sub_totals = {}
    for r in records:
        cat = r.category
        if cat.parent_id is None:
            continue
        entry = sub_totals.setdefault(cat.id, {"category": cat.name, "parent": cat.parent.name, "total": ZERO})
        entry["total"] += r.amount
    subcategory_top = sorted(({**e, "total": _q(e["total"])} for e in sub_totals.values()),
                             key=lambda e: e["total"], reverse=True)[:10]

    tag_totals = {}
    for r in records:
        if not r.tag:
            continue
        entry = tag_totals.setdefault(r.tag.name, {"tag": r.tag.name, "total": ZERO, "count": 0})
        entry["total"] += r.amount
        entry["count"] += 1
    tag_rank = sorted(({**e, "total": _q(e["total"])} for e in tag_totals.values()),
                      key=lambda e: e["total"], reverse=True)[:10]

    total_expense = _q(sum((r.amount for r in records), ZERO))
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
        "subcategory_top": subcategory_top,
        "tag_rank": tag_rank,
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
            "years": [], "yearly": [], "category_rank": [], "subcategory_top": [],
            "tag_rank": [], "stack_cats": [], "cat_year_matrix": {},
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
    cat_totals = {}
    for r in expenses:
        top = _top_category(r.category)
        entry = cat_totals.setdefault(top.id, {"category": top.name, "icon": top.icon, "total": ZERO})
        entry["total"] += r.amount
    category_rank = sorted(cat_totals.values(), key=lambda e: e["total"], reverse=True)
    for row in category_rank:
        row["total"] = _q(row["total"])
        row["pct"] = _q(row["total"] / total_expense * 100) if total_expense else ZERO

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

    # 二级分类全时段 Top 10
    sub_totals = {}
    for r in expenses:
        cat = r.category
        if cat.parent_id is None:
            continue
        entry = sub_totals.setdefault(cat.id, {"category": cat.name, "parent": cat.parent.name, "total": ZERO})
        entry["total"] += r.amount
    subcategory_top = sorted(({**e, "total": _q(e["total"])} for e in sub_totals.values()),
                             key=lambda e: e["total"], reverse=True)[:10]

    # 标签全时段榜
    tag_totals = {}
    for r in expenses:
        if not r.tag:
            continue
        entry = tag_totals.setdefault(r.tag.name, {"tag": r.tag.name, "total": ZERO, "count": 0})
        entry["total"] += r.amount
        entry["count"] += 1
    tag_rank = sorted(({**e, "total": _q(e["total"])} for e in tag_totals.values()),
                      key=lambda e: e["total"], reverse=True)[:10]

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
        "subcategory_top": subcategory_top,
        "tag_rank": tag_rank,
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
