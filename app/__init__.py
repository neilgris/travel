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
    from .models.day import transport_label, transport_emoji
    app.jinja_env.filters["transport_label"] = transport_label
    app.jinja_env.filters["transport_emoji"] = transport_emoji
    from .services.flags import country_flag
    app.jinja_env.filters["country_flag"] = country_flag
    from .blueprints import register_blueprints
    register_blueprints(app)
    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()
        _ensure_added_columns()
        _ensure_added_indexes()
    return app


# 项目不用 migration（DECISIONS D6）：模型改了直接 create_all 重建。但 create_all 只
# 建新表，不会给已存在的表补列——库里已有真实数据、删不得时，新增的可空列在这里手动补。
# 每项 (表, 列, SQL 类型)，已存在就跳过，故可重复执行。
_ADDED_COLUMNS = [
    ("expense_tag", "group_name", "VARCHAR(20)"),
    ("expense_record", "rule_id", "INTEGER"),
]


def _ensure_added_columns():
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    for table, column, sql_type in _ADDED_COLUMNS:
        if not inspector.has_table(table):
            continue  # 新库：create_all 已按模型建好，本来就带这列
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
        db.session.commit()


# create_all 同样不会给已存在的表补索引。模型里新加的唯一约束在老库上得手动建，否则
# 「自动补记的幂等由数据库兜底」这句话只对新库成立。每项 (表, 索引名, 建表语句)。
_ADDED_INDEXES = [
    ("expense_record", "uq_expense_record_rule_date",
     "CREATE UNIQUE INDEX uq_expense_record_rule_date ON expense_record (rule_id, date)"),
    ("expense_record", "ix_expense_record_rule_id",
     "CREATE INDEX ix_expense_record_rule_id ON expense_record (rule_id)"),
]


def _ensure_added_indexes():
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    for table, index, sql in _ADDED_INDEXES:
        if not inspector.has_table(table):
            continue
        if index in {i["name"] for i in inspector.get_indexes(table)}:
            continue
        db.session.execute(text(sql))
        db.session.commit()
