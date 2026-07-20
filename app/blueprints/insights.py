"""跨旅程的回顾视图：人生足迹总览 + 年度报告。

只读路由，取数全部走 services.lifetime。设计见
docs/specs/2026-07-17-insights-design.md。
"""
from flask import Blueprint, abort, render_template

from app.blueprints._json import safe_json
from app.models.day import CATEGORIES
from app.models.trip import Trip
from app.services.lifetime import lifetime_stats, year_report

bp = Blueprint("insights", __name__, url_prefix="/insights")


@bp.route("/")
def overview():
    trips = Trip.query.order_by(Trip.start_date.desc()).all()
    s = lifetime_stats(trips)
    chart_trips = [{
        "id": r["id"],
        "title": r["title"],
        "total": float(r["total_cny"]),
        "start": r["start_date"].isoformat(),
        "end": r["end_date"].isoformat(),
        "days": (r["end_date"] - r["start_date"]).days + 1,
        "by_category": {cat: float(v) for cat, v in r["by_category"].items()},
    } for r in s["trips"]]
    years = [{
        "year": r["year"],
        "total": float(r["total_cny"]),
        "trip_count": r["trip_count"],
        "distance_km": r["distance_km"],
        "days_on_road": r["days_on_road"],
    } for r in s["by_year"]]
    return render_template(
        "insights/overview.html",
        s=s,
        categories=CATEGORIES,
        chart_trips_json=safe_json(chart_trips),
        global_cat_json=safe_json({cat: float(v) for cat, v
                                    in s["global_by_category"].items()}),
        years_json=safe_json(years),
        busiest_year=s["busiest_year"],
    )


@bp.route("/<int:year>")
def year_report_page(year):
    trips = Trip.query.order_by(Trip.start_date).all()
    r = year_report(trips, year)
    if r is None:
        abort(404)
    return render_template("insights/year.html", r=r, categories=CATEGORIES,
                           map_json=safe_json(r["map"]),
                           cat_json=safe_json({cat: float(v) for cat, v
                                                in r["by_category"].items()}))
