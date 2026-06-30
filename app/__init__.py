import os
from flask import Flask
from .config import Config
from .extensions import db


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config_overrides is not None:
        app.config.update(config_overrides)
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.init_app(app)
    from .blueprints import register_blueprints
    register_blueprints(app)
    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()
    return app
