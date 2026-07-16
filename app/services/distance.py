"""旅程里程：把每个 Leg 的出发城市→到达城市直线距离累加。

只反映城市间大圆(直线)距离之和，不是实际交通路线里程。缺经纬度的段跳过
（和首页地球弧线的口径一致，见 services/globe.py）。
"""
from math import radians, sin, cos, asin, sqrt

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lng1, lat2, lng2):
    """两点大圆距离，单位公里。"""
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def has_coords(city):
    return city is not None and city.latitude is not None and city.longitude is not None


def trip_distance_km(trip):
    """旅程里程：各行程段直线距离之和，四舍五入到整数公里。"""
    total = 0.0
    for leg in trip.legs:
        frm, to = leg.from_city, leg.to_city
        if has_coords(frm) and has_coords(to):
            total += haversine_km(frm.latitude, frm.longitude,
                                  to.latitude, to.longitude)
    return round(total)
