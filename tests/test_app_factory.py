from app import create_app

def test_create_app_testing_config():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert app.testing is True

def test_create_app_has_db():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    from app.extensions import db
    with app.app_context():
        assert db.engine is not None
