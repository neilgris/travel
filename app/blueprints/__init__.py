def register_blueprints(app):
    from .main import bp as main_bp
    from .trips import bp as trips_bp
    from .settings import bp as settings_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(trips_bp)
    app.register_blueprint(settings_bp)
