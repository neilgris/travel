import datetime as dt
import json
from decimal import Decimal
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, abort)
from app.extensions import db
from app.models.trip import Trip, Leg, TripCurrency
from app.models.city import City
from app.models.person import Person
from app.models.day import Day, Entry, EntryImage, CATEGORIES, TRANSPORT_MODES
from app.services.stats import trip_stats
from app.services.uploads import save_upload

bp = Blueprint("trips", __name__, url_prefix="/trips")


def _parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


@bp.route("/")
def list():
    trips = Trip.query.order_by(Trip.start_date.desc()).all()
    summaries = {t.id: trip_stats(t)["total_cny"] for t in trips}
    return render_template("trips/list.html", trips=trips, summaries=summaries)


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
        if not froms[i] and not tos[i]:
            continue
        trip.legs.append(Leg(
            seq=int(seqs[i] or i + 1),
            from_city_id=int(froms[i]) if froms[i] else None,
            to_city_id=int(tos[i]) if tos[i] else None,
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
                           modes=TRANSPORT_MODES)


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
                           modes=TRANSPORT_MODES)


@bp.route("/<int:trip_id>")
def detail(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    return render_template("trips/detail.html", trip=trip,
                           stats=trip_stats(trip), categories=CATEGORIES)


@bp.route("/<int:trip_id>/days", methods=["POST"])
def add_day(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    day = Day(trip_id=trip.id,
              date=_parse_date(request.form["date"]),
              city_id=int(request.form["city_id"]) if request.form.get("city_id") else None,
              diary=request.form.get("diary") or None)
    db.session.add(day)
    db.session.commit()
    flash("已添加一天")
    return redirect(url_for("trips.detail", trip_id=trip.id))


@bp.route("/<int:trip_id>/days/<int:day_id>/entries", methods=["POST"])
def add_entry(trip_id, day_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    entry = Entry(day_id=day.id,
                  category=request.form["category"],
                  title=request.form["title"].strip(),
                  description=request.form.get("description") or None,
                  amount=Decimal(request.form.get("amount") or "0"),
                  currency_code=request.form.get("currency_code", "CNY").upper())
    for f in request.files.getlist("images"):
        rel = save_upload(f, current_app.config["UPLOAD_FOLDER"])
        if rel:
            entry.images.append(EntryImage(path=rel))
    db.session.add(entry)
    db.session.commit()
    flash("已添加记录")
    return redirect(url_for("trips.detail", trip_id=trip_id))


@bp.route("/<int:trip_id>/stats")
def stats_page(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    s = trip_stats(trip)
    # Chart data below is emitted to an inline <script> via |safe in stats.html — keep it to fixed CATEGORIES names, ISO date strings, and numbers only; never add user free-text here without escaping.
    cat_labels = [k for k, v in s["by_category"].items() if v > 0]
    cat_values = [float(s["by_category"][k]) for k in cat_labels]
    day_labels = [d["date"].isoformat() for d in s["by_day"]]
    day_values = [float(d["total_cny"]) for d in s["by_day"]]
    cat_labels_json = json.dumps(cat_labels, ensure_ascii=False)
    cat_values_json = json.dumps(cat_values)
    day_labels_json = json.dumps(day_labels, ensure_ascii=False)
    day_values_json = json.dumps(day_values)
    return render_template("trips/stats.html", trip=trip, stats=s,
                           cat_labels_json=cat_labels_json,
                           cat_values_json=cat_values_json,
                           day_labels_json=day_labels_json,
                           day_values_json=day_values_json)
