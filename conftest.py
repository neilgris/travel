import pytest
from sqlalchemy.pool import StaticPool
from app import create_app
from app.extensions import db as _db


@pytest.fixture
def app(tmp_path):
    # UPLOAD_FOLDER 指到临时目录，避免上传相关测试污染真实 uploads/ 目录。
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        },
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def session(app):
    with app.app_context():
        _db.create_all()
        yield _db.session
        _db.session.remove()
        _db.drop_all()
