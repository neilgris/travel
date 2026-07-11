import datetime as dt
import json
from decimal import Decimal, InvalidOperation
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, abort)
from app.extensions import db
from app.models.trip import Trip, Leg, TripCurrency
from app.models.city import City
from app.models.person import Person
from app.models.day import (Day, Entry, DayImage, CATEGORIES,
                            TRANSPORT_MODES, COMMON_CURRENCIES)
from app.services.geocoding import geocode
from app.services.exchange import fetch_rate
from app.services.stats import trip_stats, trips_overview
from app.services.uploads import save_upload, delete_upload
from app.services.import_expense import parse_rows, match_row

bp = Blueprint("trips", __name__, url_prefix="/trips")


def _parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def _resolve_city(name):
    """按城市名解析：已存在则复用，否则自动地理编码并新建。空名返回 None。"""
    name = (name or "").strip()
    if not name:
        return None
    city = City.query.filter_by(name=name).first()
    if city is None:
        coords = geocode(name)
        lat, lon = coords if coords else (None, None)
        city = City(name=name, latitude=lat, longitude=lon)
        db.session.add(city)
        db.session.flush()
    return city


@bp.route("/")
def list():
    trips = Trip.query.order_by(Trip.start_date.desc()).all()
    overview = trips_overview(trips)
    # 旅程标题是用户自由文本，进内联 <script> 前统一走 _safe_json 转义（同 stats 页）。
    chart_trips = [{
        "id": r["id"],
        "title": r["title"],
        "total": float(r["total_cny"]),
        "start": r["start_date"].isoformat(),
        "end": r["end_date"].isoformat(),
        "days": (r["end_date"] - r["start_date"]).days + 1,
        "by_category": {cat: float(v) for cat, v in r["by_category"].items()},
    } for r in overview["trips"]]
    global_cat = {cat: float(v) for cat, v in overview["global_by_category"].items()}
    return render_template(
        "trips/list.html",
        overview=overview,
        categories=CATEGORIES,
        chart_trips_json=_safe_json(chart_trips),
        global_cat_json=_safe_json(global_cat),
    )


def _apply_form(trip):
    trip.title = request.form["title"].strip()
    trip.start_date = _parse_date(request.form["start_date"])
    trip.end_date = _parse_date(request.form["end_date"])
    trip.notes = request.form.get("notes") or None
    # legs
    trip.legs = []
    seqs = request.form.getlist("leg_seq")
    froms = request.form.getlist("leg_from")
    tos = request.form.getlist("leg_to")
    modes = request.form.getlist("leg_mode")
    for i in range(len(seqs)):
        from_city = _resolve_city(froms[i])
        to_city = _resolve_city(tos[i])
        if from_city is None and to_city is None:
            continue
        trip.legs.append(Leg(
            seq=int(seqs[i] or i + 1),
            from_city=from_city,
            to_city=to_city,
            transport_mode=modes[i] or None))
    # currencies
    trip.currencies = []
    for code, rate in zip(request.form.getlist("cur_code"),
                          request.form.getlist("cur_rate")):
        if code.strip() and rate.strip():
            trip.currencies.append(TripCurrency(
                currency_code=code.strip().upper(), rate=Decimal(rate)))
    # people
    pids = [int(x) for x in request.form.getlist("people")]
    trip.people = Person.query.filter(Person.id.in_(pids)).all() if pids else []


@bp.route("/exchange-rate")
def exchange_rate():
    """前端选币种时实时查汇率（1 人民币 = ? 外币）。"""
    code = request.args.get("code", "")
    rate = fetch_rate(code)
    return {"code": code.strip().upper(), "rate": str(rate) if rate is not None else None}


@bp.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        trip = Trip(title="", start_date=dt.date.today(), end_date=dt.date.today())
        _apply_form(trip)
        db.session.add(trip)
        db.session.commit()
        flash("旅程已创建")
        return redirect(url_for("trips.detail", trip_id=trip.id))
    return render_template("trips/form.html", trip=None,
                           cities=City.query.order_by(City.name).all(),
                           people=Person.query.order_by(Person.name).all(),
                           modes=TRANSPORT_MODES,
                           currency_options=COMMON_CURRENCIES)


@bp.route("/<int:trip_id>/edit", methods=["GET", "POST"])
def edit(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    if request.method == "POST":
        _apply_form(trip)
        db.session.commit()
        flash("旅程已更新")
        return redirect(url_for("trips.detail", trip_id=trip.id))
    return render_template("trips/form.html", trip=trip,
                           cities=City.query.order_by(City.name).all(),
                           people=Person.query.order_by(Person.name).all(),
                           modes=TRANSPORT_MODES,
                           currency_options=COMMON_CURRENCIES)


@bp.route("/<int:trip_id>/delete", methods=["POST"])
def delete(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    db.session.delete(trip)
    db.session.commit()
    flash("旅程已删除")
    return redirect(url_for("trips.list"))


@bp.route("/<int:trip_id>/entries/clear", methods=["POST"])
def clear_expenses(trip_id):
    """清空整个旅程的所有消费记录（各天的 Entry），照片和日记保留。"""
    trip = db.get_or_404(Trip, trip_id)
    count = 0
    for day in trip.days:
        for entry in day.entries[:]:
            db.session.delete(entry)
            count += 1
    db.session.commit()
    flash(f"已清空 {count} 条消费记录")
    return redirect(url_for("trips.detail", trip_id=trip.id))


@bp.route("/<int:trip_id>")
def detail(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    # 「添加一天」日期默认：已有天则取最后一天次日，否则旅程首日。
    next_day_date = trip.start_date
    if trip.days:
        next_day_date = max(d.date for d in trip.days) + dt.timedelta(days=1)
    return render_template("trips/detail.html", trip=trip, next_day_date=next_day_date,
                           stats=trip_stats(trip), categories=CATEGORIES)


@bp.route("/<int:trip_id>/days", methods=["POST"])
def add_day(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    day = Day(trip_id=trip.id,
              date=_parse_date(request.form["date"]),
              city_id=int(request.form["city_id"]) if request.form.get("city_id") else None,
              diary=request.form.get("diary") or None)
    for f in request.files.getlist("images"):
        rel = save_upload(f, current_app.config["UPLOAD_FOLDER"])
        if rel:
            day.images.append(DayImage(path=rel))
    db.session.add(day)
    db.session.commit()
    flash("已添加一天")
    return redirect(url_for("trips.detail", trip_id=trip.id))


@bp.route("/<int:trip_id>/days/<int:day_id>/edit", methods=["POST"])
def edit_day(trip_id, day_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    day.date = _parse_date(request.form["date"])
    day.city_id = int(request.form["city_id"]) if request.form.get("city_id") else None
    day.diary = request.form.get("diary") or None
    db.session.commit()
    flash("已更新这一天")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/<int:trip_id>/days/<int:day_id>/delete", methods=["POST"])
def delete_day(trip_id, day_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    # 连带删除当天配图的物理文件（Entry / DayImage 记录由 cascade 清理）。
    for img in day.images:
        delete_upload(img.path, current_app.config["UPLOAD_FOLDER"])
    db.session.delete(day)
    db.session.commit()
    flash("已删除这一天")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/<int:trip_id>/days/<int:day_id>/images", methods=["POST"])
def add_day_images(trip_id, day_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    added = 0
    for f in request.files.getlist("images"):
        rel = save_upload(f, current_app.config["UPLOAD_FOLDER"])
        if rel:
            day.images.append(DayImage(path=rel))
            added += 1
    db.session.commit()
    flash(f"已添加 {added} 张照片" if added else "未选择照片")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/<int:trip_id>/days/<int:day_id>/images/<int:image_id>/delete", methods=["POST"])
def delete_day_image(trip_id, day_id, image_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    img = db.get_or_404(DayImage, image_id)
    if img.day_id != day_id:
        abort(404)
    delete_upload(img.path, current_app.config["UPLOAD_FOLDER"])
    db.session.delete(img)
    db.session.commit()
    flash("已删除照片")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/<int:trip_id>/days/<int:day_id>/entries", methods=["POST"])
def add_entry(trip_id, day_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    next_order = max((e.sort_order for e in day.entries), default=-1) + 1
    entry = Entry(day_id=day.id,
                  category=request.form["category"],
                  title=request.form["title"].strip(),
                  description=request.form.get("description") or None,
                  amount=Decimal(request.form.get("amount") or "0"),
                  currency_code=request.form.get("currency_code", "CNY").upper(),
                  sort_order=next_order)
    db.session.add(entry)
    db.session.commit()
    flash("已添加记录")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/<int:trip_id>/days/<int:day_id>/entries/<int:entry_id>/edit", methods=["POST"])
def edit_entry(trip_id, day_id, entry_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    entry = db.get_or_404(Entry, entry_id)
    if entry.day_id != day_id:
        abort(404)
    entry.category = request.form["category"]
    entry.title = request.form["title"].strip()
    entry.amount = Decimal(request.form.get("amount") or "0")
    entry.currency_code = request.form.get("currency_code", "CNY").upper()
    entry.description = request.form.get("description") or None
    # 允许把记录改到本旅程的另一天；非法/跨旅程的 new_day_id 忽略，留在原天。
    new_day_id = request.form.get("new_day_id")
    if new_day_id:
        try:
            nid = int(new_day_id)
        except ValueError:
            nid = None
        if nid in {d.id for d in day.trip.days}:
            entry.day_id = nid
    db.session.commit()
    flash("已更新记录")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/<int:trip_id>/days/<int:day_id>/entries/<int:entry_id>/delete", methods=["POST"])
def delete_entry(trip_id, day_id, entry_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    entry = db.get_or_404(Entry, entry_id)
    if entry.day_id != day_id:
        abort(404)
    db.session.delete(entry)
    db.session.commit()
    flash("已删除记录")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/<int:trip_id>/days/<int:day_id>/entries/reorder", methods=["POST"])
def reorder_entries(trip_id, day_id):
    """异步调整某天内 Entry 的显示顺序。请求体 JSON: {"order": [entry_id, ...]}。"""
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    data = request.get_json(silent=True) or {}
    raw = data.get("order")
    # 注意：本文件有个视图函数叫 list（见 bp.route("/")），遮蔽了内建 list，
    # 故这里不用 isinstance(_, list)，改用 try 迭代来校验载荷。
    if raw is None or isinstance(raw, (str, bytes, dict)):
        return {"ok": False, "error": "bad payload"}, 400
    try:
        order = [int(x) for x in raw]
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad payload"}, 400
    entries = {e.id: e for e in day.entries}
    # 提交的 id 必须恰好是本天的全部 Entry，防止漏项/串天导致顺序错乱。
    if set(order) != set(entries):
        return {"ok": False, "error": "id mismatch"}, 400
    for i, eid in enumerate(order):
        entries[eid].sort_order = i
    db.session.commit()
    return {"ok": True}


def _safe_json(obj):
    # 城市名等是用户自由文本，要进内联 <script>。转义 < > & 防止 </script> 截断/注入，
    # 同时保留 ensure_ascii=False 让中文可读。数字/固定类别名不受影响。
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


@bp.route("/<int:trip_id>/stats")
def stats_page(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    s = trip_stats(trip)
    # 下面的数据经 |safe 注入内联 <script>；含用户自由文本（城市名）时一律走 _safe_json 转义。
    # Top 10 消费含标题（自由文本），改在模板里用 Jinja 自动转义渲染，不进 JS。
    cat_labels = [k for k, v in s["by_category"].items() if v > 0]
    cat_values = [float(s["by_category"][k]) for k in cat_labels]
    day_labels = [d["date"].isoformat() for d in s["by_day"]]
    day_values = [float(d["total_cny"]) for d in s["by_day"]]
    cumulative_values = [float(d["total_cny"]) for d in s["cumulative"]]
    city_labels = [c["city"] for c in s["by_city"]]
    city_values = [float(c["cny"]) for c in s["by_city"]]
    return render_template("trips/stats.html", trip=trip, stats=s,
                           cat_labels_json=_safe_json(cat_labels),
                           cat_values_json=_safe_json(cat_values),
                           day_labels_json=_safe_json(day_labels),
                           day_values_json=_safe_json(day_values),
                           cumulative_values_json=_safe_json(cumulative_values),
                           city_labels_json=_safe_json(city_labels),
                           city_values_json=_safe_json(city_values),
                           total_cny_float=float(s["total_cny"]))


@bp.route("/<int:trip_id>/import", methods=["GET", "POST"])
def import_expenses(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("请选择要上传的 .xls 文件")
            return redirect(url_for("trips.import_expenses", trip_id=trip.id))
        rows = parse_rows(file)
        unmatched = []
        matched_count = 0
        for row in rows:
            matched, resolved = match_row(trip, row)
            if matched:
                db.session.add(Entry(day_id=resolved["day_id"], category=resolved["category"],
                                     title=resolved["title"], amount=resolved["amount"],
                                     currency_code=resolved["currency_code"]))
                matched_count += 1
            else:
                unmatched.append(resolved)
        db.session.commit()
        msg = f"自动导入 {matched_count} 条"
        if unmatched:
            msg += f"，{len(unmatched)} 条待确认"
        flash(msg)
        if unmatched:
            days = sorted(trip.days, key=lambda d: d.date)
            return render_template("trips/import_review.html", trip=trip,
                                   unmatched=unmatched, categories=CATEGORIES, days=days)
        return redirect(url_for("trips.detail", trip_id=trip.id))
    return render_template("trips/import.html", trip=trip)


@bp.route("/<int:trip_id>/import/confirm", methods=["POST"])
def import_confirm(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    valid_day_ids = {d.id for d in trip.days}
    valid_currencies = {"CNY"} | {c.currency_code for c in trip.currencies}
    # 这五个平行列表按行下标对齐：import_review.html 每个待确认行都恰好为每个
    # 字段名各产出一个表单项（title/amount 恒有；day_id/category/currency_code
    # 各产出一个 hidden 或一个 select）。若改模板使某字段条件性渲染，会错位到别的条目。
    titles = request.form.getlist("title")
    amounts = request.form.getlist("amount")
    day_ids = request.form.getlist("day_id")
    categories_in = request.form.getlist("category")
    currencies_in = request.form.getlist("currency_code")
    count = 0
    for i in range(len(titles)):
        try:
            day_id = int(day_ids[i]) if day_ids[i] else None
            amount = Decimal(amounts[i])
        except (ValueError, InvalidOperation):
            continue
        category = categories_in[i]
        currency_code = currencies_in[i]
        if day_id not in valid_day_ids or category not in CATEGORIES or currency_code not in valid_currencies:
            continue
        db.session.add(Entry(day_id=day_id, category=category,
                             title=titles[i][:200], amount=amount,
                             currency_code=currency_code))
        count += 1
    db.session.commit()
    flash(f"已确认导入 {count} 条")
    return redirect(url_for("trips.detail", trip_id=trip.id))
