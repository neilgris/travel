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


def yearly_stats(year):
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

    return {
        "year": year,
        "monthly": monthly,
        "category_rank": category_rank,
        "subcategory_top": subcategory_top,
        "tag_rank": tag_rank,
        "total_expense": total_expense,
        "total_income": total_income,
        "balance": _q(total_income - total_expense),
        "avg_month_expense": _q(total_expense / 12),
        "avg_day_expense": _q(total_expense / 365),
        "max_single": max_single,
        "days_with_expense": days_with_expense,
    }
