"""人生足迹总览与年度报告的聚合层。

两个页面（/insights/ 与 /insights/<year>）共用这一层，口径只在这里定义一次：

- 年份归属：整趟按 start_date 的年份，不按天拆分。库里仅 1 趟跨年旅程
  （201612 - 台北，2016-12-29 → 2017-01-02），按天拆会让同一趟同时出现在
  两年的报告里，叙事别扭且旅程数与总览页对不上，为 2 天不值得。见 DECISIONS D21。
- 在途天数：(end_date - start_date + 1) 求和，重叠日期去重（当前数据无重叠，防御性）。
- 新解锁国家：该国家首次到访旅程的 start_date 年份。
- 国家计数：City.country 字段值原样计数，同 stats.trips_overview 既有口径。

金额换算复用 services.stats，里程复用 services.distance，均不重写。
设计见 docs/specs/2026-07-17-insights-design.md。
"""
import datetime as dt

from app.services.distance import trip_distance_km
from app.services.stats import trips_overview

# 住处：most_visited_city 的排除项、farthest_city 的距离基准。
# 与 stats.trips_overview 里 top_cities 排除北京的口径一致。
HOME_CITY = "北京"
CHINA = "中国"


def _sorted(trips):
    """按开始日期升序，同日期按 id 兜底（同 blueprints/trips.py 的相邻旅程口径）。"""
    return sorted(trips, key=lambda t: (t.start_date, t.id))


def _trip_dates(trip):
    """一趟旅程覆盖的日期集合，含首尾。"""
    n = (trip.end_date - trip.start_date).days
    return {trip.start_date + dt.timedelta(days=i) for i in range(n + 1)}


def _days_on_road(trips):
    """在途天数：各旅程日期跨度并集的大小（重叠日期只算一天）。"""
    days = set()
    for t in trips:
        days |= _trip_dates(t)
    return len(days)


def lifetime_stats(trips):
    """人生足迹总览页数据：trips_overview 的全部键 + 里程/在途天数/里程碑/逐年。"""
    overview = trips_overview(trips)
    return {
        **overview,
        "total_distance_km": sum(trip_distance_km(t) for t in trips),
        "days_on_road": _days_on_road(trips),
    }
