import datetime as dt
from app.models.city import City
from app.models.trip import Trip


def seed_cities(app):
    from app.extensions import db
    with app.app_context():
        bj = City(name="北京")
        hk = City(name="香港")
        db.session.add_all([bj, hk])
        db.session.commit()
        return bj.id, hk.id


def test_create_trip(client, app):
    bj_id, hk_id = seed_cities(app)
    resp = client.post("/trips/create", data={
        "title": "测试之旅",
        "start_date": "2026-01-01", "end_date": "2026-01-05",
        "notes": "note",
        "leg_seq": ["1"], "leg_from": [str(bj_id)], "leg_to": [str(hk_id)],
        "leg_mode": ["飞机"],
        "cur_code": ["HKD"], "cur_rate": ["1.1"],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        t = Trip.query.filter_by(title="测试之旅").one()
        assert len(t.legs) == 1
        assert t.transport_modes == ["飞机"]
        assert t.currencies[0].currency_code == "HKD"


def test_list_shows_trip(client, app):
    seed_cities(app)
    client.post("/trips/create", data={
        "title": "展示之旅", "start_date": "2026-02-01", "end_date": "2026-02-03",
    }, follow_redirects=True)
    resp = client.get("/trips/")
    assert "展示之旅" in resp.get_data(as_text=True)
