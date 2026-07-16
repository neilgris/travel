"""跨旅程的回顾视图：人生足迹总览 + 年度报告。

只读路由，取数全部走 services.lifetime。设计见
docs/specs/2026-07-17-insights-design.md。
"""
import json

from flask import Blueprint, render_template

from app.models.day import CATEGORIES
from app.models.trip import Trip
from app.services.lifetime import lifetime_stats

bp = Blueprint("insights", __name__, url_prefix="/insights")


def _safe_json(obj):
    # 旅程标题/城市名是用户自由文本，要进内联 <script>。转义 < > & 防止 </script>
    # 截断/注入，同时保留 ensure_ascii=False 让中文可读。同 blueprints/trips.py。
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


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
        chart_trips_json=_safe_json(chart_trips),
        global_cat_json=_safe_json({cat: float(v) for cat, v
                                    in s["global_by_category"].items()}),
        years_json=_safe_json(years),
        busiest_year=s["busiest_year"],
    )
