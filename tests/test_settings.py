from unittest.mock import patch
from app.models.person import Person
from app.models.city import City


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
