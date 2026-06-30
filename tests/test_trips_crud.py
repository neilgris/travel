import datetime as dt
from unittest.mock import patch
from app.models.city import City
from app.models.trip import Trip
from app.extensions import db


def seed_cities(app):
    from app.extensions import db
    with app.app_context():
        bj = City(name="北京")
        hk = City(name="香港")
        db.session.add_all([bj, hk])
        db.session.commit()
        return bj.id, hk.id


def test_create_trip(client, app):
    seed_cities(app)
    resp = client.post("/trips/create", data={
        "title": "测试之旅",
        "start_date": "2026-01-01", "end_date": "2026-01-05",
        "notes": "note",
        "leg_seq": ["1"], "leg_from": ["北京"], "leg_to": ["香港"],
        "leg_mode": ["飞机"],
        "cur_code": ["HKD"], "cur_rate": ["1.1"],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        t = Trip.query.filter_by(title="测试之旅").one()
        assert len(t.legs) == 1
        assert t.legs[0].from_city.name == "北京"
        assert t.legs[0].to_city.name == "香港"
        assert t.transport_modes == ["飞机"]
        assert t.currencies[0].currency_code == "HKD"


def test_create_trip_creates_new_city_inline(client, app):
    """行程段输入一个未维护的新城市名时，应自动地理编码并创建该城市。"""
    seed_cities(app)
    with patch("app.blueprints.trips.geocode", return_value=(35.01, 135.77)):
        resp = client.post("/trips/create", data={
            "title": "京都之旅",
            "start_date": "2026-04-01", "end_date": "2026-04-03",
            "leg_seq": ["1"], "leg_from": ["香港"], "leg_to": ["京都"],
            "leg_mode": ["飞机"],
        }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        kyoto = City.query.filter_by(name="京都").one()
        assert kyoto.latitude == 35.01 and kyoto.longitude == 135.77
        t = Trip.query.filter_by(title="京都之旅").one()
        assert t.legs[0].to_city.name == "京都"


def test_create_trip_reuses_existing_city_by_name(client, app):
    """输入已存在城市名时复用，不重复创建。"""
    seed_cities(app)
    with patch("app.blueprints.trips.geocode") as mock_geo:
        client.post("/trips/create", data={
            "title": "复用之旅",
            "start_date": "2026-05-01", "end_date": "2026-05-02",
            "leg_seq": ["1"], "leg_from": ["北京"], "leg_to": ["香港"],
            "leg_mode": ["火车"],
        }, follow_redirects=True)
    mock_geo.assert_not_called()
    with app.app_context():
        assert City.query.filter_by(name="北京").count() == 1
        assert City.query.filter_by(name="香港").count() == 1


def test_edit_trip(client, app):
    seed_cities(app)
    client.post("/trips/create", data={
        "title": "原标题", "start_date": "2026-03-01", "end_date": "2026-03-02",
    }, follow_redirects=True)
    with app.app_context():
        tid = Trip.query.filter_by(title="原标题").one().id
    resp = client.post(f"/trips/{tid}/edit", data={
        "title": "新标题", "start_date": "2026-03-01", "end_date": "2026-03-02",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Trip, tid).title == "新标题"


def test_list_shows_trip(client, app):
    seed_cities(app)
    client.post("/trips/create", data={
        "title": "展示之旅", "start_date": "2026-02-01", "end_date": "2026-02-03",
    }, follow_redirects=True)
    resp = client.get("/trips/")
    assert "展示之旅" in resp.get_data(as_text=True)
