from app.models.city import City

def test_city_persists(session):
    c = City(name="札幌", latitude=43.06, longitude=141.35, country="日本")
    session.add(c); session.commit()
    assert c.id is not None
    assert City.query.filter_by(name="札幌").one().latitude == 43.06
