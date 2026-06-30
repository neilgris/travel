from app.models.person import Person

def test_person_persists(session):
    p = Person(name="老婆", photo="uploads/wife.jpg")
    session.add(p); session.commit()
    assert p.id is not None
    assert Person.query.filter_by(name="老婆").one().photo == "uploads/wife.jpg"
