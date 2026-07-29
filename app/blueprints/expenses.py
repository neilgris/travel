"""日常消费模块：流水增删改、导入、月度/年度统计、分类与标签管理。
与旅程模块数据层零关联。设计见 docs/specs/2026-07-20-daily-expense-design.md。
"""
import datetime as dt
from decimal import Decimal, InvalidOperation
from itertools import groupby

from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort,
                   jsonify, current_app)
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.blueprints._json import safe_json
from app.models.expense import (ExpenseCategory, ExpenseTag, ExpenseRecord, ExpenseRule,
                                EXPENSE_KINDS, TAG_GROUPS, seed_default_categories,
                                seed_tag_groups, guess_icon)
from app.services.expense_import import (parse_rows, import_rows, record_natural_key,
                                          next_free_fingerprint, refresh_all_fingerprints,
                                          compact_fingerprints_around)
from app.services.expense_recurring import materialize, next_due, preview, run_if_stale
from app.services.expense_stats import (monthly_stats, yearly_stats, overview_stats,
                                         trend_stats, trend_year_records)

bp = Blueprint("expenses", __name__, url_prefix="/expenses")


@bp.before_request
def _ensure_categories():
    seed_default_categories()
    seed_tag_groups()


@bp.before_request
def _catch_up_recurring():
    """进日常消费模块时把固定收支补到今天。每天首次请求才真跑，其余直接返回。"""
    run_if_stale(current_app)


def _parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def _parse_month(s):
    """<input type="month"> 交上来的 YYYY-MM → 当月 1 号。"""
    return dt.datetime.strptime(s, "%Y-%m").date().replace(day=1)


def _category_tree(kind=None):
    # 模板会挨个访问 top.children；不预加载的话每个一级分类都要单独查一次子分类。
    q = ExpenseCategory.query.filter_by(parent_id=None).options(selectinload(ExpenseCategory.children))
    if kind:
        q = q.filter_by(kind=kind)
    return q.order_by(ExpenseCategory.sort_order, ExpenseCategory.id).all()


def _category_tree_json():
    return safe_json([{
        "id": top.id, "name": top.name, "kind": top.kind, "icon": top.icon,
        "children": [{"id": sub.id, "name": sub.name, "icon": sub.icon} for sub in top.children],
    } for top in _category_tree()])


def _rec_json(r):
    return {"date": r["date"].isoformat(), "note": r["note"], "category": r["category"],
            "tag": r["tag"], "amount": float(r["amount"])}


def _board_json(board):
    """一级/二级/标签榜（同构：排行项 + 单笔 records）→ 内联 JSON。
    Decimal→float、date→iso；yoy 拍平成 yoy_pct，其余标量字段（name/parent/icon/count/tag）原样带过。"""
    out = []
    for b in board:
        node = {k: (float(v) if isinstance(v, Decimal) else v)
                for k, v in b.items() if k not in ("records", "yoy")}
        node["records"] = [_rec_json(r) for r in b["records"]]
        if "yoy" in b:
            node["yoy_pct"] = float(b["yoy"]["pct"]) if b["yoy"]["pct"] is not None else None
        out.append(node)
    return out


def _tag_sections():
    """分类管理页的标签分组展示：[(组名或 None, [标签,...]), ...]，按 TAG_GROUPS 定义的
    顺序排列；未分组统一放最后一节（组名 None，模板显示「未分组」）。TAG_GROUPS 改动后
    库里可能还残留旧组名（比如某个组被整个下掉），这类"野"组名也照样展示、排在末尾，
    不会因为不在当前 TAG_GROUPS 里就把标签悄悄藏起来。"""
    by_group = {}
    for t in ExpenseTag.query.order_by(ExpenseTag.name).all():
        by_group.setdefault(t.group_name, []).append(t)
    sections = [(g, by_group[g]) for g in TAG_GROUPS if by_group.get(g)]
    stray = sorted(g for g in by_group if g is not None and g not in TAG_GROUPS)
    sections += [(g, by_group[g]) for g in stray]
    if by_group.get(None):
        sections.append((None, by_group[None]))
    return sections


def _recent_years(n=10):
    # 模块里 `list` 这个名字被下面的视图函数 list() 遮住了，这里不能调 list(range(...))
    current = dt.date.today().year
    return [current - i for i in range(n)]


def _filtered_query(args):
    """流水筛选条件的唯一实现：list() 渲染页面、bulk_edit() 圈定批量操作范围都走这条，
    保证"当前筛选出来的所有记录"两处算出来是同一批。返回 (query, filters)。"""
    kind = args.get("kind") or None
    ym = args.get("ym") or None
    if ym:
        year = None
    elif "year" in args:
        year = args.get("year", type=int)  # 显式选了"全部"时 year= 是空串，取不到数字 -> None
    elif not args:
        year = dt.date.today().year  # 真正第一次进来（不带任何参数）：默认只看当年，流水量太大会拖慢首屏
    else:
        year = None  # 带了别的筛选参数（如只给 q/kind）但没给 year，不额外强加当年限制
    category_ids = args.getlist("category_id", type=int)
    tag_q = (args.get("tag_q") or "").strip()
    q = (args.get("q") or "").strip()

    query = ExpenseRecord.query
    if kind:
        query = query.filter_by(kind=kind)
    if ym:
        try:
            ym_year, month = (int(x) for x in ym.split("-"))
            start = dt.date(ym_year, month, 1)
            end = (dt.date(ym_year + 1, 1, 1) if month == 12 else dt.date(ym_year, month + 1, 1)) - dt.timedelta(days=1)
            query = query.filter(ExpenseRecord.date >= start, ExpenseRecord.date <= end)
        except ValueError:
            pass
    elif year:
        query = query.filter(ExpenseRecord.date >= dt.date(year, 1, 1), ExpenseRecord.date <= dt.date(year, 12, 31))
    if category_ids:
        expanded = set(category_ids)
        tops = ExpenseCategory.query.filter(ExpenseCategory.id.in_(category_ids),
                                            ExpenseCategory.parent_id.is_(None)).all()
        for top in tops:
            expanded.update(c.id for c in top.children)
        query = query.filter(ExpenseRecord.category_id.in_(expanded))
    if tag_q == "空":
        query = query.filter(ExpenseRecord.tag_id.is_(None))
    elif tag_q:
        query = query.join(ExpenseTag, ExpenseRecord.tag_id == ExpenseTag.id).filter(
            ExpenseTag.name.ilike(f"%{tag_q}%"))
    if q:
        query = query.filter(ExpenseRecord.note.ilike(f"%{q}%"))

    filters = {"kind": kind, "ym": ym, "year": year, "category_id": category_ids, "tag_q": tag_q, "q": q}
    return query, filters


@bp.route("/")
def list():
    query, filters = _filtered_query(request.args)
    records = query.order_by(ExpenseRecord.date.desc(), ExpenseRecord.created_at.desc()).all()

    # groups: [{ym, records, subtotal, days}]；days 供「筛了单月」时按日再分组用
    # （days: [{date, records, subtotal}]）
    groups = []
    for r in records:
        ym_key = f"{r.date.year}-{r.date.month:02d}"
        if not groups or groups[-1]["ym"] != ym_key:
            label = f"{r.date.year % 100}年{r.date.month}月"
            groups.append({"ym": ym_key, "label": label, "records": [], "subtotal": Decimal("0.00"), "days": []})
        g = groups[-1]
        g["records"].append(r)
        if r.kind == "支出":
            g["subtotal"] += r.amount
        if not g["days"] or g["days"][-1]["date"] != r.date:
            g["days"].append({"date": r.date, "records": [], "subtotal": Decimal("0.00")})
        day = g["days"][-1]
        day["records"].append(r)
        if r.kind == "支出":
            day["subtotal"] += r.amount

    template = ("expenses/_list_results.html" if request.headers.get("X-Requested-With") == "XMLHttpRequest"
                else "expenses/list.html")
    return render_template(template, groups=groups, total_count=len(records),
                           kinds=EXPENSE_KINDS, categories=_category_tree(), years=_recent_years(),
                           tags=ExpenseTag.query.order_by(ExpenseTag.name).all(),
                           categories_json=_category_tree_json(), today=dt.date.today(),
                           filters=filters)


def _record_fingerprint(record, category, tag):
    """手工新增/编辑/批量改之后重算指纹。自然键怎么归一化由 services 那边的
    record_natural_key 一家说了算——导入、重刷走的是同一个函数，口径只有一份。"""
    return next_free_fingerprint(record_natural_key(record, category, tag),
                                 exclude_id=record.id)


def _apply_record_form(record):
    """把提交的表单写进 record；成功返回 None，失败返回错误信息（不再直接 flash，
    XHR 场景要把这条消息塞进 JSON 而不是走 flash）。"""
    kind = request.form["kind"]
    if kind not in EXPENSE_KINDS:
        abort(400)
    category = db.session.get(ExpenseCategory, request.form.get("category_id", type=int) or 0)
    if category is None or category.kind != kind:
        return "请选择有效的分类"
    try:
        amount = Decimal(request.form["amount"])
    except (InvalidOperation, KeyError):
        return "金额格式不对"
    tag_name = (request.form.get("tag_name") or "").strip()
    tag = None
    if tag_name:
        tag = ExpenseTag.query.filter_by(name=tag_name).first()
        if tag is None:
            tag = ExpenseTag(name=tag_name)
            db.session.add(tag)
            db.session.flush()
    date = _parse_date(request.form["date"])
    note = request.form.get("note") or None
    record.kind = kind
    record.date = date
    record.category_id = category.id
    record.tag_id = tag.id if tag else None
    record.amount = amount
    record.note = note
    record.fingerprint = _record_fingerprint(record, category, tag)
    return None


@bp.route("/new", methods=["GET", "POST"])
def create():
    is_xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if request.method == "POST":
        record = ExpenseRecord(source="manual")
        error = _apply_record_form(record)
        if not error:
            db.session.add(record)
            db.session.commit()
            if is_xhr:
                # 只回 id：列表随后整体按当前筛选重刷，前端拿 id 判断这条有没有落进筛选范围
                return jsonify(ok=True, id=record.id)
            flash("已添加记录")
            return redirect(url_for("expenses.list"))
        if is_xhr:
            return jsonify(ok=False, error=error), 400
        flash(error)
    return render_template("expenses/form.html", record=None, kinds=EXPENSE_KINDS,
                           categories_json=_category_tree_json(), today=dt.date.today(),
                           tags=ExpenseTag.query.order_by(ExpenseTag.name).all())


@bp.route("/<int:record_id>/edit", methods=["GET", "POST"])
def edit(record_id):
    record = db.get_or_404(ExpenseRecord, record_id)
    is_xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if request.method == "POST":
        error = _apply_record_form(record)
        if not error:
            db.session.commit()
            if is_xhr:
                return jsonify(ok=True, html=render_template("expenses/_item_row.html", r=record))
            flash("已更新记录")
            return redirect(url_for("expenses.list"))
        if is_xhr:
            return jsonify(ok=False, error=error), 400
        flash(error)
    if is_xhr:
        return render_template("expenses/_inline_edit_form.html", record=record,
                               kinds=EXPENSE_KINDS, tags=ExpenseTag.query.order_by(ExpenseTag.name).all())
    return render_template("expenses/form.html", record=record, kinds=EXPENSE_KINDS,
                           categories_json=_category_tree_json(), today=dt.date.today(),
                           tags=ExpenseTag.query.order_by(ExpenseTag.name).all())


@bp.route("/<int:record_id>/delete", methods=["POST"])
def delete(record_id):
    record = db.get_or_404(ExpenseRecord, record_id)
    is_xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    db.session.delete(record)
    db.session.commit()
    # 删掉的如果是「同天同分类同金额同备注」多笔里的一条，会在指纹序号里留个空洞，
    # 剩下那条得往前挪补上（详见 compact_fingerprints_around），不然去重会漏判。
    compact_fingerprints_around(record)
    if is_xhr:
        return jsonify(ok=True)
    flash("已删除记录")
    return redirect(url_for("expenses.list"))


@bp.route("/bulk-edit", methods=["POST"])
def bulk_edit():
    """批量把「当前筛选出来的所有记录」的分类或标签改成同一个值。范围复用
    _filtered_query，跟流水页正在显示的筛选结果完全一致——不是另外勾选的一批。"""
    is_xhr = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    field = request.form.get("field")
    query, _ = _filtered_query(request.form)
    records = query.all()

    if field == "category":
        category = db.session.get(ExpenseCategory, request.form.get("value", type=int) or 0)
        if category is None:
            error = "请选择有效的分类"
            if is_xhr:
                return jsonify(ok=False, error=error), 400
            flash(error)
            return redirect(url_for("expenses.list"))
        updated = skipped = 0
        for r in records:
            if r.kind != category.kind:  # 分类的收支类型跟记录对不上，不能硬改
                skipped += 1
                continue
            r.category_id = category.id
            r.fingerprint = _record_fingerprint(r, category, r.tag)
            updated += 1
        db.session.commit()
        msg = f"已批量修改分类：{updated} 条"
        if skipped:
            msg += f"，跳过 {skipped} 条（收支类型与目标分类不符）"
    elif field == "tag":
        tag_name = (request.form.get("value") or "").strip()
        tag = None
        if tag_name:
            tag = ExpenseTag.query.filter_by(name=tag_name).first()
            if tag is None:
                tag = ExpenseTag(name=tag_name)
                db.session.add(tag)
                db.session.flush()
        for r in records:
            r.tag_id = tag.id if tag else None
            r.fingerprint = _record_fingerprint(r, r.category, tag)
        db.session.commit()
        msg = f"已批量{'清空' if not tag else '修改'}标签：{len(records)} 条"
    else:
        error = "未知的批量操作字段"
        if is_xhr:
            return jsonify(ok=False, error=error), 400
        flash(error)
        return redirect(url_for("expenses.list"))

    if is_xhr:
        return jsonify(ok=True, message=msg)
    flash(msg)
    return redirect(url_for("expenses.list"))


@bp.route("/monthly")
def monthly():
    today = dt.date.today()
    ym = request.args.get("ym") or f"{today.year}-{today.month:02d}"
    year, month = (int(x) for x in ym.split("-"))
    s = monthly_stats(year, month)
    prev = (dt.date(year, month, 1) - dt.timedelta(days=1))
    nxt_month_first = (dt.date(year, 12, 31) + dt.timedelta(days=1)) if month == 12 else dt.date(year, month + 1, 1)
    # 下拉可选年月：有流水的月份 + 当前所看月 + 本月，按年分组、倒序
    # 注意：本模块的 list 名被视图函数 list() 遮住，这里用 [*ms] 而非 list(ms)
    months = sorted(_data_months() | {ym, f"{today.year}-{today.month:02d}"}, reverse=True)
    month_groups = [(yr, [*ms]) for yr, ms in groupby(months, key=lambda m: m[:4])]
    return render_template("expenses/monthly.html", s=s, ym=ym,
                           prev_ym=f"{prev.year}-{prev.month:02d}",
                           next_ym=f"{nxt_month_first.year}-{nxt_month_first.month:02d}",
                           month_groups=month_groups,
                           cat_json=safe_json([{"category": c["category"], "total": float(c["total"])}
                                               for c in s["by_category"]]),
                           cat1_json=safe_json(_board_json(s["cat1_board"])),
                           cat2_json=safe_json(_board_json(s["cat2_board"])),
                           tag_drill_json=safe_json(_board_json(s["tag_drill"])),
                           daily_json=safe_json([{"date": d["date"].isoformat(), "total": float(d["total"])}
                                                 for d in s["daily"]]))


@bp.route("/yearly")
def yearly():
    year = request.args.get("year", type=int) or dt.date.today().year
    s = yearly_stats(year)
    cur_month = dt.date.today().month if year == dt.date.today().year else 12
    # 下拉可选年份：有流水的年 + 当前所看年 + 今年，倒序
    year_options = sorted(set(_data_years()) | {year, dt.date.today().year}, reverse=True)
    return render_template("expenses/yearly.html", s=s, year=year, cur_month=cur_month,
                           year_options=year_options,
                           monthly_json=safe_json([{"month": m["month"], "expense": float(m["expense"]),
                                                    "income": float(m["income"])} for m in s["monthly"]]),
                           cat_json=safe_json([{"category": c["category"], "total": float(c["total"])}
                                               for c in s["category_rank"]]),
                           cat1_json=safe_json(_board_json(s["cat1_board"])),
                           cat2_json=safe_json(_board_json(s["cat2_board"])),
                           tag_drill_json=safe_json(_board_json(s["tag_drill"])))


@bp.route("/overview")
def overview():
    s = overview_stats()
    yearly_json = safe_json([{"year": r["year"], "expense": float(r["expense"]),
                              "income": float(r["income"])} for r in s["yearly"]])
    stacked_json = safe_json({
        "years": s["years"],
        "series": [{"category": name, "data": [float(v) for v in s["cat_year_matrix"][name]]}
                   for name in s["stack_cats"]],
    })
    cat_json = safe_json([{"category": c["category"], "total": float(c["total"])}
                          for c in s["category_rank"]])
    return render_template("expenses/overview.html", s=s,
                           yearly_json=yearly_json, stacked_json=stacked_json, cat_json=cat_json,
                           cat1_json=safe_json(_board_json(s["cat1_board"])),
                           cat2_json=safe_json(_board_json(s["cat2_board"])),
                           tag_drill_json=safe_json(_board_json(s["tag_drill"])))


@bp.route("/trends")
def trends():
    s = trend_stats()
    data = {
        "years": s["years"],
        "default_key": s["default_key"],
        "dimensions": [{
            "key": d["key"], "type": d["type"], "kind": d["kind"], "name": d["name"],
            "icon": d["icon"], "parent": d["parent"], "parent_key": d.get("parent_key"),
            "group": d.get("group"), "group_icon": d.get("group_icon"),
            "subgroup": d.get("subgroup"),
            "total": float(d["total"]),
            "amounts": [float(a) for a in d["amounts"]], "counts": d["counts"],
        } for d in s["dimensions"]],
    }
    return render_template("expenses/trends.html", trend_json=safe_json(data),
                           has_data=bool(s["dimensions"]))


@bp.route("/trends/records")
def trend_records():
    key = request.args.get("key") or ""
    year = request.args.get("year", type=int)
    if not key or not year:
        return jsonify(records=[])
    recs = trend_year_records(key, year, limit=50)
    return jsonify(records=[_rec_json(r) for r in recs])


@bp.route("/import", methods=["GET", "POST"])
def import_file():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("请选择文件")
            return redirect(url_for("expenses.import_file"))
        rows = parse_rows(f)
        result = import_rows(rows)
        flash(f"导入完成：新增 {result['created']} 条 · 跳过 {result['skipped']} 条重复 · "
              f"新建分类 {result['new_categories']} 个 · 新建标签 {result['new_tags']} 个")
        return redirect(url_for("expenses.list"))
    return render_template("expenses/import.html", data_years=_data_years())


def _data_years():
    rows = db.session.query(db.func.strftime("%Y", ExpenseRecord.date)).distinct().all()
    return sorted({int(r[0]) for r in rows}, reverse=True)


def _data_months():
    """有流水的年月集合，形如 {'2025-11', ...}。给月度页下拉用。"""
    rows = db.session.query(db.func.strftime("%Y-%m", ExpenseRecord.date)).distinct().all()
    return {r[0] for r in rows}


@bp.route("/refresh-fingerprints", methods=["POST"])
def refresh_fingerprints():
    result = refresh_all_fingerprints()
    if result["changed"]:
        flash(f"指纹重刷完成：共核对 {result['total']} 条 · 更新 {result['changed']} 条")
    else:
        flash(f"指纹重刷完成：共核对 {result['total']} 条，全部已是最新，无需更新")
    return redirect(url_for("expenses.import_file"))


@bp.route("/clear", methods=["POST"])
def clear():
    year = request.form.get("year", type=int)
    query = ExpenseRecord.query
    if year:
        query = query.filter(ExpenseRecord.date >= dt.date(year, 1, 1), ExpenseRecord.date <= dt.date(year, 12, 31))
    count = query.delete(synchronize_session=False)
    db.session.commit()
    flash(f"已清空{f'{year} 年' if year else '全部'} {count} 条记录")
    return redirect(url_for("expenses.import_file"))


@bp.route("/categories", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        name = request.form["name"].strip()
        kind = request.form["kind"]
        parent_id = request.form.get("parent_id", type=int)
        if not name or kind not in EXPENSE_KINDS:
            flash("请填写完整")
            return redirect(url_for("expenses.categories"))
        parent = db.session.get(ExpenseCategory, parent_id) if parent_id else None
        if parent and parent.parent_id is not None:
            flash("只能挂在一级分类下")
            return redirect(url_for("expenses.categories"))
        exists = ExpenseCategory.query.filter_by(
            kind=kind, parent_id=parent.id if parent else None, name=name).first()
        if exists:
            flash("同级下已有同名分类")
            return redirect(url_for("expenses.categories"))
        icon = request.form.get("icon") or guess_icon(name)
        db.session.add(ExpenseCategory(name=name, kind=kind, parent_id=parent.id if parent else None,
                                       icon=icon))
        db.session.commit()
        flash("已添加分类")
        return redirect(url_for("expenses.categories"))
    return render_template("expenses/categories.html", categories=_category_tree(),
                           tag_sections=_tag_sections(), tag_groups=TAG_GROUPS)


@bp.route("/categories/<int:cat_id>/edit", methods=["POST"])
def edit_category(cat_id):
    cat = db.get_or_404(ExpenseCategory, cat_id)
    name = request.form["name"].strip()
    if not name:
        flash("名称不能为空")
        return redirect(url_for("expenses.categories"))
    cat.name = name
    cat.icon = request.form.get("icon") or None
    sort_order = request.form.get("sort_order", type=int)
    if sort_order is not None:
        cat.sort_order = sort_order
    db.session.commit()
    flash("已更新分类")
    return redirect(url_for("expenses.categories"))


@bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
def delete_category(cat_id):
    cat = db.get_or_404(ExpenseCategory, cat_id)
    in_use = ExpenseRecord.query.filter_by(category_id=cat_id).count()
    if cat.children or in_use:
        flash(f"无法删除：{cat.name} 下还有子分类或已被流水使用")
        return redirect(url_for("expenses.categories"))
    db.session.delete(cat)
    db.session.commit()
    flash("已删除分类")
    return redirect(url_for("expenses.categories"))


@bp.route("/tags/<int:tag_id>/edit", methods=["POST"])
def edit_tag(tag_id):
    tag = db.get_or_404(ExpenseTag, tag_id)
    group = request.form.get("group_name") or None
    if group is not None and group not in TAG_GROUPS:
        abort(400)
    tag.group_name = group
    db.session.commit()
    flash(f"#{tag.name} 已归到「{group or '未分组'}」")
    return redirect(url_for("expenses.categories"))


@bp.route("/tags/<int:tag_id>/delete", methods=["POST"])
def delete_tag(tag_id):
    tag = db.get_or_404(ExpenseTag, tag_id)
    in_use = ExpenseRecord.query.filter_by(tag_id=tag_id).count()
    if in_use:
        flash(f"无法删除：{tag.name} 已被 {in_use} 条流水使用")
        return redirect(url_for("expenses.categories"))
    db.session.delete(tag)
    db.session.commit()
    flash("已删除标签")
    return redirect(url_for("expenses.categories"))


# --- 固定收支规则 ---------------------------------------------------------

def _flat_category_options():
    """规则表单用的扁平分类列表。逐行编辑用一个下拉就够，不值得为它再搭一套级联。"""
    options = []
    for top in _category_tree():
        options.append({"id": top.id, "kind": top.kind,
                        "label": f"{top.icon or ''} {top.name}".strip()})
        for sub in top.children:
            options.append({"id": sub.id, "kind": sub.kind,
                            "label": f"{top.name} / {sub.icon or ''} {sub.name}".strip()})
    return options


def _apply_rule_form(rule):
    """把表单写进 rule；成功返回 None，失败返回错误信息。"""
    kind = request.form.get("kind")
    if kind not in EXPENSE_KINDS:
        abort(400)
    category = db.session.get(ExpenseCategory, request.form.get("category_id", type=int) or 0)
    if category is None or category.kind != kind:
        return "请选择有效的分类"
    try:
        amount = Decimal(request.form["amount"])
    except (InvalidOperation, KeyError):
        return "金额格式不对"
    if amount <= 0:
        return "金额要大于 0"
    interval = request.form.get("interval_months", type=int) or 1
    if not 1 <= interval <= 60:
        return "间隔月数要在 1~60 之间"
    try:
        start_month = _parse_month(request.form["start_month"])
    except (ValueError, KeyError):
        return "请填写起始月"
    end_month = None
    if (request.form.get("end_month") or "").strip():
        try:
            end_month = _parse_month(request.form["end_month"])
        except ValueError:
            return "结束月格式不对"
        if end_month < start_month:
            return "结束月不能早于起始月"

    tag_name = (request.form.get("tag_name") or "").strip()
    tag = None
    if tag_name:
        tag = ExpenseTag.query.filter_by(name=tag_name).first()
        if tag is None:
            tag = ExpenseTag(name=tag_name)
            db.session.add(tag)
            db.session.flush()

    rule.name = (request.form.get("name") or "").strip() or category.name
    rule.kind = kind
    rule.category_id = category.id
    rule.tag_id = tag.id if tag else None
    rule.amount = amount
    rule.interval_months = interval
    rule.start_month = start_month
    rule.end_month = end_month
    rule.note = request.form.get("note") or None
    return None


@bp.route("/rules", methods=["GET", "POST"])
def rules():
    if request.method == "POST":
        rule = ExpenseRule()
        error = _apply_rule_form(rule)
        if error:
            db.session.rollback()
            flash(error)
            return redirect(url_for("expenses.rules"))
        db.session.add(rule)
        db.session.commit()
        created = materialize(rule)
        flash(f"已添加规则「{rule.name}」" + (f"，补记 {len(created)} 条" if created else ""))
        return redirect(url_for("expenses.rules"))

    today = dt.date.today()
    rows = [{
        "rule": rule,
        "generated": ExpenseRecord.query.filter_by(rule_id=rule.id).count(),
        "next": next_due(rule, today) if rule.active else None,
    } for rule in ExpenseRule.query.order_by(ExpenseRule.active.desc(), ExpenseRule.kind,
                                             ExpenseRule.id)]
    return render_template("expenses/rules.html", rows=rows, kinds=EXPENSE_KINDS,
                           flat_categories=_flat_category_options(),
                           this_month=today.strftime("%Y-%m"),
                           tags=ExpenseTag.query.order_by(ExpenseTag.name).all())


@bp.route("/rules/preview")
def rule_preview():
    """建规则前算一眼会补多少条——纯计算，不写库。"""
    try:
        draft = ExpenseRule(
            amount=Decimal(request.args.get("amount") or "0"),
            interval_months=request.args.get("interval_months", type=int) or 1,
            start_month=_parse_month(request.args["start_month"]),
            end_month=(_parse_month(request.args["end_month"])
                       if (request.args.get("end_month") or "").strip() else None),
        )
    except (InvalidOperation, ValueError, KeyError):
        return jsonify(ok=False), 400
    p = preview(draft)
    return jsonify(ok=True, count=p["count"], total=float(p["total"]),
                   first=p["first"].isoformat() if p["first"] else None,
                   last=p["last"].isoformat() if p["last"] else None)


@bp.route("/rules/<int:rule_id>/edit", methods=["POST"])
def edit_rule(rule_id):
    rule = db.get_or_404(ExpenseRule, rule_id)
    error = _apply_rule_form(rule)
    if error:
        db.session.rollback()
        flash(error)
        return redirect(url_for("expenses.rules"))
    db.session.commit()
    # 改金额只影响以后：已生成的记录留着当时的数，因为那才是当时真实发生的。
    created = materialize(rule)
    flash(f"已更新规则「{rule.name}」" + (f"，补记 {len(created)} 条" if created else ""))
    return redirect(url_for("expenses.rules"))


@bp.route("/rules/<int:rule_id>/toggle", methods=["POST"])
def toggle_rule(rule_id):
    rule = db.get_or_404(ExpenseRule, rule_id)
    rule.active = not rule.active
    db.session.commit()
    if rule.active:
        created = materialize(rule)
        flash(f"已启用「{rule.name}」" + (f"，补记 {len(created)} 条" if created else ""))
    else:
        flash(f"已停用「{rule.name}」，已生成的记录保留")
    return redirect(url_for("expenses.rules"))


@bp.route("/rules/<int:rule_id>/delete", methods=["POST"])
def delete_rule(rule_id):
    """删规则时顺带给一条后悔路：连它生成的记录一起删掉。"""
    rule = db.get_or_404(ExpenseRule, rule_id)
    name = rule.name
    generated = ExpenseRecord.query.filter_by(rule_id=rule_id)
    if request.form.get("purge"):
        removed = generated.delete(synchronize_session=False)
        message = f"已删除规则「{name}」及它生成的 {removed} 条记录"
    else:
        # 记录留下，但要断开关联，否则外键指向一条已经不存在的规则。
        generated.update({"rule_id": None, "source": "manual"}, synchronize_session=False)
        message = f"已删除规则「{name}」，它生成的记录转为手工记录保留"
    db.session.delete(rule)
    db.session.commit()
    flash(message)
    return redirect(url_for("expenses.rules"))
