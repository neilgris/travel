"""跨旅程的回顾视图：人生足迹总览 + 年度报告。

只读路由，取数全部走 services.lifetime。设计见
docs/specs/2026-07-17-insights-design.md。
"""
from flask import Blueprint, render_template

from app.models.day import CATEGORIES
from app.models.trip import Trip
from app.services.lifetime import lifetime_stats

bp = Blueprint("insights", __name__, url_prefix="/insights")


@bp.route("/")
def overview():
    trips = Trip.query.order_by(Trip.start_date.desc()).all()
    return render_template("insights/overview.html",
                           s=lifetime_stats(trips), categories=CATEGORIES)
