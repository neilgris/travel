import datetime as dt

from app.models.trip import Trip
from app.services.globe import build_globe_data, TRIP_PALETTE


def test_globe_trips_sorted_recent_first(session):
    """右侧旅程列表按开始日期倒序：最近的排在前面。"""
    session.add_all([
        Trip(title="老", start_date=dt.date(2025, 1, 1), end_date=dt.date(2025, 1, 5)),
        Trip(title="中", start_date=dt.date(2026, 3, 1), end_date=dt.date(2026, 3, 5)),
        Trip(title="新", start_date=dt.date(2026, 7, 1), end_date=dt.date(2026, 7, 5)),
    ])
    session.commit()

    titles = [t["title"] for t in build_globe_data()["trips"]]
    assert titles == ["新", "中", "老"]


def test_globe_trip_colors_stable_by_start_date(session):
    """配色仍按 start_date 升序循环取，倒序列表不应打乱每个旅程的颜色。"""
    session.add_all([
        Trip(title="老", start_date=dt.date(2025, 1, 1), end_date=dt.date(2025, 1, 5)),
        Trip(title="新", start_date=dt.date(2026, 7, 1), end_date=dt.date(2026, 7, 5)),
    ])
    session.commit()

    colors = {t["title"]: t["color"] for t in build_globe_data()["trips"]}
    assert colors["老"] == TRIP_PALETTE[0]
    assert colors["新"] == TRIP_PALETTE[1]
