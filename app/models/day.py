import datetime as dt
from app.extensions import db

CATEGORIES = ["吃饭", "游玩", "购物", "住宿", "交通"]
TRANSPORT_MODES = ["飞机", "火车", "游轮", "自驾", "大巴", "步行", "其他"]

# 常见外币（人民币为默认本币，不在此列）。(代码, 中文名, 国旗)
COMMON_CURRENCIES = [
    ("JPY", "日元", "🇯🇵"), ("USD", "美元", "🇺🇸"), ("EUR", "欧元", "🇪🇺"),
    ("HKD", "港币", "🇭🇰"), ("GBP", "英镑", "🇬🇧"), ("KRW", "韩元", "🇰🇷"),
    ("THB", "泰铢", "🇹🇭"), ("SGD", "新加坡元", "🇸🇬"), ("AUD", "澳元", "🇦🇺"),
    ("CAD", "加元", "🇨🇦"), ("CHF", "瑞士法郎", "🇨🇭"), ("TWD", "新台币", "🇹🇼"),
    ("MOP", "澳门元", "🇲🇴"), ("MYR", "林吉特", "🇲🇾"), ("NZD", "新西兰元", "🇳🇿"),
    ("VND", "越南盾", "🇻🇳"), ("IDR", "印尼盾", "🇮🇩"), ("PHP", "菲律宾比索", "🇵🇭"),
    ("INR", "印度卢比", "🇮🇳"), ("RUB", "俄罗斯卢布", "🇷🇺"), ("AED", "迪拉姆", "🇦🇪"),
    ("EGP", "埃及镑", "🇪🇬"), ("TRY", "土耳其里拉", "🇹🇷"),
]


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
    created_at = db.Column(db.DateTime, default=lambda: dt.datetime.now(dt.timezone.utc))

    images = db.relationship("EntryImage", backref="entry",
                             cascade="all, delete-orphan")


class EntryImage(db.Model):
    __tablename__ = "entry_image"
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.ForeignKey("entry.id"), nullable=False)
    path = db.Column(db.String(255), nullable=False)
