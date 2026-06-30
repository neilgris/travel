import datetime as dt
from app.extensions import db

CATEGORIES = ["吃饭", "游玩", "购物", "住宿", "交通"]
TRANSPORT_MODES = ["飞机", "火车", "游轮", "自驾", "大巴", "步行", "其他"]


class Day(db.Model):
    __tablename__ = "day"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.ForeignKey("trip.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    city_id = db.Column(db.ForeignKey("city.id"))
    diary = db.Column(db.Text)

    city = db.relationship("City")
    entries = db.relationship("Entry", backref="day", order_by="Entry.created_at",
                              cascade="all, delete-orphan")


class Entry(db.Model):
    __tablename__ = "entry"
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.ForeignKey("day.id"), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    currency_code = db.Column(db.String(10), nullable=False, default="CNY")
    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    images = db.relationship("EntryImage", backref="entry",
                             cascade="all, delete-orphan")


class EntryImage(db.Model):
    __tablename__ = "entry_image"
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.ForeignKey("entry.id"), nullable=False)
    path = db.Column(db.String(255), nullable=False)
