import datetime as dt
from unittest.mock import patch
from app.extensions import db
from app.models.person import Person
from app.models.city import City
from app.models.trip import Trip, Leg
from app.models.day import Day


def test_add_person(client, app):
    resp = client.post("/settings/people", data={"name": "老婆"},
                       follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Person.query.filter_by(name="老婆").count() == 1


def test_add_city_geocodes(client, app):
    with patch("app.blueprints.settings.geocode", return_value=(43.06, 141.35)):
        client.post("/settings/cities", data={"name": "札幌"},
                    follow_redirects=True)
    with app.app_context():
        c = City.query.filter_by(name="札幌").one()
        assert c.latitude == 43.06 and c.longitude == 141.35


def test_add_city_no_coords(client, app):
    with patch("app.blueprints.settings.geocode", return_value=None):
        resp = client.post("/settings/cities", data={"name": "未知城市"},
                           follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = City.query.filter_by(name="未知城市").one()
        assert c.latitude is None and c.longitude is None


# ---------- 同行人：编辑 / 删除 ----------

def test_edit_person_renames(client, app):
    with app.app_context():
        p = Person(name="旧名")
        db.session.add(p)
        db.session.commit()
        pid = p.id
    resp = client.post(f"/settings/people/{pid}/edit",
                       data={"name": "新名"}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Person, pid).name == "新名"


def test_delete_person(client, app):
    with app.app_context():
        p = Person(name="待删")
        db.session.add(p)
        db.session.commit()
        pid = p.id
    client.post(f"/settings/people/{pid}/delete", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Person, pid) is None


def test_delete_person_in_use_blocked(client, app):
    with app.app_context():
        p = Person(name="同行")
        t = Trip(title="旅程", start_date=dt.date(2026, 1, 1),
                 end_date=dt.date(2026, 1, 2))
        t.people.append(p)
        db.session.add_all([p, t])
        db.session.commit()
        pid = p.id
    client.post(f"/settings/people/{pid}/delete", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Person, pid) is not None


# ---------- 城市：编辑 / 删除 ----------

def test_edit_city_fields(client, app):
    with app.app_context():
        c = City(name="旧城", country="旧国")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    resp = client.post(f"/settings/cities/{cid}/edit",
                       data={"name": "新城", "country": "新国",
                             "latitude": "1.5", "longitude": "2.5"},
                       follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        c = db.session.get(City, cid)
        assert c.name == "新城" and c.country == "新国"
        assert c.latitude == 1.5 and c.longitude == 2.5


def test_edit_city_regeocode(client, app):
    with app.app_context():
        c = City(name="待定位")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    with patch("app.blueprints.settings.geocode", return_value=(10.0, 20.0)):
        client.post(f"/settings/cities/{cid}/edit",
                    data={"name": "待定位", "regeocode": "1"},
                    follow_redirects=True)
    with app.app_context():
        c = db.session.get(City, cid)
        assert c.latitude == 10.0 and c.longitude == 20.0


def test_delete_city(client, app):
    with app.app_context():
        c = City(name="待删城")
        db.session.add(c)
        db.session.commit()
        cid = c.id
    client.post(f"/settings/cities/{cid}/delete", follow_redirects=True)
    with app.app_context():
        assert db.session.get(City, cid) is None


def test_delete_city_in_leg_blocked(client, app):
    with app.app_context():
        c = City(name="腿城")
        t = Trip(title="旅程", start_date=dt.date(2026, 1, 1),
                 end_date=dt.date(2026, 1, 2))
        db.session.add_all([c, t])
        db.session.commit()
        db.session.add(Leg(trip_id=t.id, seq=1, from_city_id=c.id))
        db.session.commit()
        cid = c.id
    client.post(f"/settings/cities/{cid}/delete", follow_redirects=True)
    with app.app_context():
        assert db.session.get(City, cid) is not None


def test_delete_city_in_day_blocked(client, app):
    with app.app_context():
        c = City(name="某天城")
        t = Trip(title="旅程", start_date=dt.date(2026, 1, 1),
                 end_date=dt.date(2026, 1, 2))
        db.session.add_all([c, t])
        db.session.commit()
        db.session.add(Day(trip_id=t.id, date=dt.date(2026, 1, 1),
                           city_id=c.id))
        db.session.commit()
        cid = c.id
    client.post(f"/settings/cities/{cid}/delete", follow_redirects=True)
    with app.app_context():
        assert db.session.get(City, cid) is not None
