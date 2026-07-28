"""日常消费的月度/年度统计聚合层。所有金额均为人民币 Decimal，两位四舍五入。
纯查询，无 HTTP，供 blueprints/expenses.py 调用。设计见
docs/specs/2026-07-20-daily-expense-design.md。
"""
import calendar
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseRecord, ExpenseTag

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


# 走势页专用：一次算出所有维度（一级/二级/标签）各自的逐年金额与笔数序列，客户端切换单条折线。
# 排序分组：支出一级 → 支出二级 → 收入一级 → 收入二级 → 标签，组内按累计金额降序，供下拉分组用。
_TREND_GROUP_RANK = {("cat1", "支出"): 0, ("cat2", "支出"): 1,
                     ("cat1", "收入"): 2, ("cat2", "收入"): 3, ("tag", None): 4}


def trend_stats():
    """所有分类/标签维度的逐年走势。返回 {years, dimensions, default_key}：
    - years：全量记账跨度 first_year..last_year（含无数据的中间年），各维度共用一条时间轴；
    - dimensions：每项 {key, type(cat1/cat2/tag), kind, name, icon, parent, total, amounts[], counts[]}，
      amounts/counts 与 years 一一对应，某年无消费补 0；
    - default_key：累计金额最高的维度，进页面默认选中。
    标签跨支出/收入汇总，kind 为 None，另带两级归属供走势页左栏缩进展示：
    - group/group_icon = 它花得最多的那个一级分类（标签不挂在分类树上，只能按金额推）；
    - subgroup = 手工设的标签组（菜系/火锅/甜品饮品…，见 ExpenseTag.group_name），未设为 None。
    标签排序：一级分类组合计 → 标签组合计（未分组的沉底）→ 标签自身金额，均降序。
    无记录时三者分别为 [] / [] / None。"""
    records = ExpenseRecord.query.all()
    if not records:
        return {"years": [], "dimensions": [], "default_key": None}

    years = list(range(min(r.date.year for r in records), max(r.date.year for r in records) + 1))
    year_idx = {y: i for i, y in enumerate(years)}
    n = len(years)
    dims = {}
    tag_by_top = {}   # 标签 key → {一级分类 id: 该标签花在这个一级分类下的金额}
    tops = {}         # 一级分类 id → 分类对象（算标签归属时取名字/图标用）

    def bucket(key, **meta):
        d = dims.get(key)
        if d is None:
            d = dims[key] = {"key": key, "amounts": [ZERO] * n, "counts": [0] * n, **meta}
        return d

    for r in records:
        i = year_idx[r.date.year]
        top = _top_category(r.category)
        tops[top.id] = top
        d1 = bucket(f"cat1-{top.id}", type="cat1", kind=top.kind, name=top.name, icon=top.icon, parent=None)
        d1["amounts"][i] += r.amount
        d1["counts"][i] += 1
        cat = r.category
        if cat.parent_id is not None:
            d2 = bucket(f"cat2-{cat.id}", type="cat2", kind=cat.kind, name=cat.name,
                        icon=cat.icon or cat.parent.icon, parent=cat.parent.name,
                        parent_key=f"cat1-{cat.parent_id}")
            d2["amounts"][i] += r.amount
            d2["counts"][i] += 1
        if r.tag:
            dt_ = bucket(f"tag-{r.tag_id}", type="tag", kind=None, name=r.tag.name, icon=None,
                         parent=None, subgroup=r.tag.group_name)
            dt_["amounts"][i] += r.amount
            dt_["counts"][i] += 1
            by_top = tag_by_top.setdefault(dt_["key"], {})
            by_top[top.id] = by_top.get(top.id, ZERO) + r.amount

    for d in dims.values():
        d["amounts"] = [_q(a) for a in d["amounts"]]
        d["total"] = _q(sum(d["amounts"], ZERO))

    # 标签归到它花得最多的那个一级分类；金额并列时用分类 id 定序，保证结果稳定
    group_total, sub_total = {}, {}
    for d in dims.values():
        if d["type"] != "tag":
            continue
        by_top = tag_by_top.get(d["key"], {})
        top_id = max(by_top, key=lambda cid: (by_top[cid], -cid))
        top = tops[top_id]
        d["group"], d["group_icon"] = top.name, top.icon
        group_total[top.name] = group_total.get(top.name, ZERO) + d["total"]
        if d["subgroup"]:
            sub_key = (top.name, d["subgroup"])
            sub_total[sub_key] = sub_total.get(sub_key, ZERO) + d["total"]

    def sub_rank(d):
        """标签在所属一级分类内的次级排序：有标签组的按组合计降序聚在一起，
        未分组的（subgroup 为 None）不成组，统一沉到该分类最后。"""
        if not d.get("subgroup"):
            return (1, ZERO, "")
        return (0, -sub_total[(d["group"], d["subgroup"])], d["subgroup"])

    default_key = max(dims.values(), key=lambda d: d["total"])["key"]
    # 分类维度组内按金额降序；标签先按一级分类的合计聚成大组，组内再按标签组聚成小组，
    # 最后按标签自身金额降序
    ordered = sorted(dims.values(),
                     key=lambda d: (_TREND_GROUP_RANK.get((d["type"], d["kind"]), 9),
                                    -group_total.get(d.get("group"), ZERO),
                                    sub_rank(d) if d["type"] == "tag" else (0, ZERO, ""),
                                    -d["total"]))
    return {"years": years, "dimensions": ordered, "default_key": default_key}


def trend_year_records(key, year, limit=15):
    """走势页右侧「某年 Top 消费」：给一个维度 key（cat1-<id>/cat2-<id>/tag-<id>）和年份，
    返回该维度当年金额最高的前 limit 笔（结构同各榜的 records，交蓝图序列化）。
    一级维度含其所有二级；未知前缀返回空。"""
    prefix, _, ident = key.rpartition("-")
    if not ident.isdigit():
        return []
    ident = int(ident)
    q = ExpenseRecord.query.filter(ExpenseRecord.date >= dt.date(year, 1, 1),
                                   ExpenseRecord.date <= dt.date(year, 12, 31))
    if prefix == "cat1":
        cat = db.session.get(ExpenseCategory, ident)
        ids = [ident] + [c.id for c in cat.children] if cat else [ident]
        q = q.filter(ExpenseRecord.category_id.in_(ids))
    elif prefix == "cat2":
        q = q.filter(ExpenseRecord.category_id == ident)
    elif prefix == "tag":
        q = q.filter(ExpenseRecord.tag_id == ident)
    else:
        return []
    return _top_records(q.all(), limit)
