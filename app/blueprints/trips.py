import datetime as dt
from decimal import Decimal
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash)
from app.extensions import db
from app.models.trip import Trip, Leg, TripCurrency
from app.models.city import City
from app.models.person import Person
from app.models.day import TRANSPORT_MODES
from app.services.stats import trip_stats

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


@bp.route("/<int:trip_id>")
def detail(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    return render_template("trips/detail.html", trip=trip,
                           stats=trip_stats(trip))
