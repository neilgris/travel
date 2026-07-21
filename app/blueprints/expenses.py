"""日常消费模块：流水增删改、导入、月度/年度统计、分类与标签管理。
与旅程模块数据层零关联。设计见 docs/specs/2026-07-20-daily-expense-design.md。
"""
import datetime as dt
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.blueprints._json import safe_json
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord, EXPENSE_KINDS, seed_default_categories
from app.services.expense_import import parse_rows, import_rows
from app.services.expense_stats import monthly_stats, yearly_stats

bp = Blueprint("expenses", __name__, url_prefix="/expenses")


@bp.before_request
def _ensure_categories():
    seed_default_categories()


def _parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


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


def _recent_years(n=10):
    # 模块里 `list` 这个名字被下面的视图函数 list() 遮住了，这里不能调 list(range(...))
    current = dt.date.today().year
    return [current - i for i in range(n)]


@bp.route("/")
def list():
    kind = request.args.get("kind") or None
    ym = request.args.get("ym") or None
    if ym:
        year = None
    elif "year" in request.args:
        year = request.args.get("year", type=int)  # 显式选了"全部"时 year= 是空串，取不到数字 -> None
    elif not request.args:
        year = dt.date.today().year  # 真正第一次进来（不带任何参数）：默认只看当年，流水量太大会拖慢首屏
    else:
        year = None  # 带了别的筛选参数（如只给 q/kind）但没给 year，不额外强加当年限制
    category_ids = request.args.getlist("category_id", type=int)
    tag_ids = request.args.getlist("tag_id", type=int)
    q = (request.args.get("q") or "").strip()

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
    if tag_ids:
        query = query.filter(ExpenseRecord.tag_id.in_(tag_ids))
    if q:
        query = query.filter(ExpenseRecord.note.ilike(f"%{q}%"))

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
    return render_template(template, groups=groups,
                           kinds=EXPENSE_KINDS, categories=_category_tree(), years=_recent_years(),
                           tags=ExpenseTag.query.order_by(ExpenseTag.name).all(),
                           filters={"kind": kind, "ym": ym, "year": year, "category_id": category_ids,
                                    "tag_id": tag_ids, "q": q})


def _apply_record_form(record):
    kind = request.form["kind"]
    if kind not in EXPENSE_KINDS:
        abort(400)
    category = db.session.get(ExpenseCategory, int(request.form["category_id"]))
    if category is None or category.kind != kind:
        flash("请选择有效的分类")
        return False
    try:
        amount = Decimal(request.form["amount"])
    except (InvalidOperation, KeyError):
        flash("金额格式不对")
        return False
    tag_name = (request.form.get("tag_name") or "").strip()
    tag = None
    if tag_name:
        tag = ExpenseTag.query.filter_by(name=tag_name).first()
        if tag is None:
            tag = ExpenseTag(name=tag_name)
            db.session.add(tag)
            db.session.flush()
    record.kind = kind
    record.date = _parse_date(request.form["date"])
    record.category_id = category.id
    record.tag_id = tag.id if tag else None
    record.amount = amount
    record.note = request.form.get("note") or None
    return True


@bp.route("/new", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        record = ExpenseRecord(source="manual")
        if _apply_record_form(record):
            db.session.add(record)
            db.session.commit()
            flash("已添加记录")
            return redirect(url_for("expenses.list"))
    return render_template("expenses/form.html", record=None, kinds=EXPENSE_KINDS,
                           categories_json=_category_tree_json(), today=dt.date.today(),
                           tags=ExpenseTag.query.order_by(ExpenseTag.name).all())


@bp.route("/<int:record_id>/edit", methods=["GET", "POST"])
def edit(record_id):
    record = db.get_or_404(ExpenseRecord, record_id)
    if request.method == "POST":
        if _apply_record_form(record):
            db.session.commit()
            flash("已更新记录")
            return redirect(url_for("expenses.list"))
    return render_template("expenses/form.html", record=record, kinds=EXPENSE_KINDS,
                           categories_json=_category_tree_json(), today=dt.date.today(),
                           tags=ExpenseTag.query.order_by(ExpenseTag.name).all())


@bp.route("/<int:record_id>/delete", methods=["POST"])
def delete(record_id):
    record = db.get_or_404(ExpenseRecord, record_id)
    db.session.delete(record)
    db.session.commit()
    flash("已删除记录")
    return redirect(url_for("expenses.list"))


@bp.route("/monthly")
def monthly():
    today = dt.date.today()
    ym = request.args.get("ym") or f"{today.year}-{today.month:02d}"
    year, month = (int(x) for x in ym.split("-"))
    s = monthly_stats(year, month)
    prev = (dt.date(year, month, 1) - dt.timedelta(days=1))
    nxt_month_first = (dt.date(year, 12, 31) + dt.timedelta(days=1)) if month == 12 else dt.date(year, month + 1, 1)
    return render_template("expenses/monthly.html", s=s, ym=ym,
                           prev_ym=f"{prev.year}-{prev.month:02d}",
                           next_ym=f"{nxt_month_first.year}-{nxt_month_first.month:02d}",
                           cat_json=safe_json([{"category": c["category"], "total": float(c["total"])}
                                               for c in s["by_category"]]),
                           daily_json=safe_json([{"date": d["date"].isoformat(), "total": float(d["total"])}
                                                 for d in s["daily"]]))


@bp.route("/yearly")
def yearly():
    year = request.args.get("year", type=int) or dt.date.today().year
    s = yearly_stats(year)
    return render_template("expenses/yearly.html", s=s, year=year,
                           monthly_json=safe_json([{"month": m["month"], "expense": float(m["expense"]),
                                                    "income": float(m["income"])} for m in s["monthly"]]))


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
    return render_template("expenses/import.html")


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
        db.session.add(ExpenseCategory(name=name, kind=kind, parent_id=parent.id if parent else None,
                                       icon=(request.form.get("icon") or None)))
        db.session.commit()
        flash("已添加分类")
        return redirect(url_for("expenses.categories"))
    return render_template("expenses/categories.html", categories=_category_tree(),
                           tags=ExpenseTag.query.order_by(ExpenseTag.name).all())


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
