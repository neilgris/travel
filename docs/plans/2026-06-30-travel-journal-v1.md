# 旅游记录网站 第一版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个纯私人、本地运行的旅游记录网站第一版：录入旅程/行程段/每天的记录与花费，并按旅程做花费统计（饼图+柱状图）。

**Architecture:** Flask 应用工厂 + Flask-SQLAlchemy(SQLite) 数据层 + Jinja2 服务端渲染 + Chart.js(CDN) 图表。数据层、业务逻辑（汇率换算、统计）、Web 层分离，逻辑层不依赖 Flask 请求上下文，可独立单元测试。

**Tech Stack:** Python 3.11+、Flask、Flask-SQLAlchemy、pytest、Werkzeug（文件上传）、requests（Nominatim 地理编码）、Chart.js。

## Global Constraints

- 纯私人、本地单机运行，无账号/登录/多用户。
- 数据库：SQLite 单文件，路径 `instance/travel.db`（Flask instance 目录）。
- 图片存 `uploads/`，数据库只存相对路径。
- 汇率方向恒为 `1 人民币 = ? 外币`；换算公式 `人民币 = 外币 ÷ 汇率`；人民币条目不换算。
- Entry 类别枚举固定：`吃饭/游玩/购物/住宿/交通`。
- 出行方式枚举：`飞机/火车/游轮/自驾/大巴/步行/其他`。
- Trip 的城市与出行方式不单独存储，由 Leg 推导（无 TripCity 表）。
- 所有金额用 `Numeric(12,2)`，避免浮点误差。
- 文档同步纪律：改数据模型→更新设计文档+CLAUDE.md；新取舍→DECISIONS.md。
- 权威设计：`docs/specs/2026-06-30-travel-journal-design.md`。

---

### Task 1: 项目骨架与应用工厂

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/extensions.py`
- Create: `conftest.py`
- Create: `tests/test_app_factory.py`

**Interfaces:**
- Produces: `app.create_app(config_overrides: dict | None = None) -> Flask`；`app.extensions.db`（SQLAlchemy 实例）。

- [ ] **Step 1: 写依赖文件**

`requirements.txt`:
```
Flask>=3.0
Flask-SQLAlchemy>=3.1
requests>=2.31
pytest>=8.0
```

- [ ] **Step 2: 安装依赖**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
Expected: 安装成功。

- [ ] **Step 3: 写失败测试**

`tests/test_app_factory.py`:
```python
from app import create_app

def test_create_app_testing_config():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert app.testing is True

def test_create_app_has_db():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    from app.extensions import db
    with app.app_context():
        assert db.engine is not None
```

- [ ] **Step 4: 运行测试确认失败**

Run: `pytest tests/test_app_factory.py -v`
Expected: FAIL（`No module named 'app'`）。

- [ ] **Step 5: 实现 extensions 与工厂**

`app/extensions.py`:
```python
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
```

`app/config.py`:
```python
import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

class Config:
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "instance", "travel.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
```

`app/__init__.py`:
```python
import os
from flask import Flask
from .config import Config
from .extensions import db

def create_app(config_overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.init_app(app)
    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()
    return app
```

- [ ] **Step 6: 写 conftest 占位 models**

`conftest.py`:
```python
import pytest
from app import create_app
from app.extensions import db as _db

@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
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
```

创建空 `app/models/__init__.py`（下一任务填充）。

- [ ] **Step 7: 运行测试确认通过**

Run: `pytest tests/test_app_factory.py -v`
Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add requirements.txt app/ conftest.py tests/
git commit -m "feat: Flask 应用工厂与数据库扩展"
```

---

### Task 2: City 模型与地理编码服务

**Files:**
- Create: `app/models/city.py`
- Modify: `app/models/__init__.py`
- Create: `app/services/geocoding.py`
- Create: `tests/test_city_model.py`
- Create: `tests/test_geocoding.py`

**Interfaces:**
- Produces: `City(id, name, latitude, longitude, country)`；`geocoding.geocode(name: str) -> tuple[float, float] | None`。

- [ ] **Step 1: 写 City 模型失败测试**

`tests/test_city_model.py`:
```python
from app.models.city import City

def test_city_persists(session):
    c = City(name="札幌", latitude=43.06, longitude=141.35, country="日本")
    session.add(c); session.commit()
    assert c.id is not None
    assert City.query.filter_by(name="札幌").one().latitude == 43.06
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_city_model.py -v`
Expected: FAIL（`No module named 'app.models.city'`）。

- [ ] **Step 3: 实现 City 模型**

`app/models/city.py`:
```python
from app.extensions import db

class City(db.Model):
    __tablename__ = "city"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    country = db.Column(db.String(100))

    def __repr__(self):
        return f"<City {self.name}>"
```

`app/models/__init__.py`:
```python
from .city import City  # noqa: F401
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_city_model.py -v`
Expected: PASS。

- [ ] **Step 5: 写地理编码失败测试（mock 网络）**

`tests/test_geocoding.py`:
```python
from unittest.mock import patch, MagicMock
from app.services import geocoding

def test_geocode_returns_coords():
    fake = MagicMock()
    fake.json.return_value = [{"lat": "43.06", "lon": "141.35"}]
    fake.raise_for_status.return_value = None
    with patch("app.services.geocoding.requests.get", return_value=fake):
        assert geocoding.geocode("札幌") == (43.06, 141.35)

def test_geocode_no_result_returns_none():
    fake = MagicMock()
    fake.json.return_value = []
    fake.raise_for_status.return_value = None
    with patch("app.services.geocoding.requests.get", return_value=fake):
        assert geocoding.geocode("不存在的城市xyz") is None
```

- [ ] **Step 6: 运行确认失败**

Run: `pytest tests/test_geocoding.py -v`
Expected: FAIL。

- [ ] **Step 7: 实现地理编码服务**

`app/services/__init__.py`: 空文件。
`app/services/geocoding.py`:
```python
import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def geocode(name):
    """用 OpenStreetMap Nominatim 查城市坐标，失败返回 None。"""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": name, "format": "json", "limit": 1},
            headers={"User-Agent": "travel-journal/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None
    if not data:
        return None
    return (float(data[0]["lat"]), float(data[0]["lon"]))
```

- [ ] **Step 8: 运行确认通过**

Run: `pytest tests/test_geocoding.py -v`
Expected: PASS。

- [ ] **Step 9: 提交**

```bash
git add app/models/ app/services/ tests/
git commit -m "feat: City 模型与 Nominatim 地理编码服务"
```

---

### Task 3: Person 模型

**Files:**
- Create: `app/models/person.py`
- Modify: `app/models/__init__.py`
- Create: `tests/test_person_model.py`

**Interfaces:**
- Produces: `Person(id, name, photo)`。

- [ ] **Step 1: 写失败测试**

`tests/test_person_model.py`:
```python
from app.models.person import Person

def test_person_persists(session):
    p = Person(name="老婆", photo="uploads/wife.jpg")
    session.add(p); session.commit()
    assert p.id is not None
    assert Person.query.filter_by(name="老婆").one().photo == "uploads/wife.jpg"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_person_model.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 Person 模型**

`app/models/person.py`:
```python
from app.extensions import db

class Person(db.Model):
    __tablename__ = "person"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    photo = db.Column(db.String(255))

    def __repr__(self):
        return f"<Person {self.name}>"
```

在 `app/models/__init__.py` 追加：`from .person import Person  # noqa: F401`

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_person_model.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add app/models/ tests/
git commit -m "feat: Person 同行人模型"
```

---

### Task 4: Trip、Leg、TripCurrency、TripPerson 模型

**Files:**
- Create: `app/models/trip.py`
- Modify: `app/models/__init__.py`
- Create: `tests/test_trip_model.py`

**Interfaces:**
- Consumes: `City`, `Person`。
- Produces:
  - `Trip(id, title, start_date, end_date, notes)`，关系 `legs`, `days`, `currencies`, `people`；属性 `cities -> list[City]`（去重）、`transport_modes -> list[str]`（去重）。
  - `Leg(id, trip_id, seq, from_city_id, to_city_id, transport_mode)`，关系 `from_city`, `to_city`。
  - `TripCurrency(id, trip_id, currency_code, rate)`。
  - `trip_person` 关联表。

- [ ] **Step 1: 写失败测试**

`tests/test_trip_model.py`:
```python
import datetime as dt
from app.models.trip import Trip, Leg, TripCurrency
from app.models.city import City
from app.models.person import Person

def make_cities(session):
    bj = City(name="北京"); hk = City(name="香港"); ok = City(name="冲绳")
    session.add_all([bj, hk, ok]); session.commit()
    return bj, hk, ok

def test_trip_with_legs_derives_cities_and_modes(session):
    bj, hk, ok = make_cities(session)
    t = Trip(title="测试行程", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,5))
    t.legs = [
        Leg(seq=1, from_city=bj, to_city=hk, transport_mode="飞机"),
        Leg(seq=2, from_city=hk, to_city=ok, transport_mode="游轮"),
    ]
    session.add(t); session.commit()
    assert {c.name for c in t.cities} == {"北京", "香港", "冲绳"}
    assert set(t.transport_modes) == {"飞机", "游轮"}

def test_trip_currencies_and_people(session):
    bj, hk, ok = make_cities(session)
    p = Person(name="老婆"); session.add(p)
    t = Trip(title="x", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,2))
    t.currencies = [TripCurrency(currency_code="JPY", rate=20.8)]
    t.people = [p]
    session.add(t); session.commit()
    assert t.currencies[0].currency_code == "JPY"
    assert t.people[0].name == "老婆"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_trip_model.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现模型**

`app/models/trip.py`:
```python
from app.extensions import db

trip_person = db.Table(
    "trip_person",
    db.Column("trip_id", db.ForeignKey("trip.id"), primary_key=True),
    db.Column("person_id", db.ForeignKey("person.id"), primary_key=True),
)

class Trip(db.Model):
    __tablename__ = "trip"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)

    legs = db.relationship("Leg", backref="trip", order_by="Leg.seq",
                           cascade="all, delete-orphan")
    currencies = db.relationship("TripCurrency", backref="trip",
                                 cascade="all, delete-orphan")
    days = db.relationship("Day", backref="trip", order_by="Day.date",
                           cascade="all, delete-orphan")
    people = db.relationship("Person", secondary=trip_person, backref="trips")

    @property
    def cities(self):
        seen, out = set(), []
        for leg in self.legs:
            for c in (leg.from_city, leg.to_city):
                if c and c.id not in seen:
                    seen.add(c.id); out.append(c)
        return out

    @property
    def transport_modes(self):
        out = []
        for leg in self.legs:
            if leg.transport_mode and leg.transport_mode not in out:
                out.append(leg.transport_mode)
        return out

class Leg(db.Model):
    __tablename__ = "leg"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.ForeignKey("trip.id"), nullable=False)
    seq = db.Column(db.Integer, nullable=False, default=1)
    from_city_id = db.Column(db.ForeignKey("city.id"))
    to_city_id = db.Column(db.ForeignKey("city.id"))
    transport_mode = db.Column(db.String(20))

    from_city = db.relationship("City", foreign_keys=[from_city_id])
    to_city = db.relationship("City", foreign_keys=[to_city_id])

class TripCurrency(db.Model):
    __tablename__ = "trip_currency"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.ForeignKey("trip.id"), nullable=False)
    currency_code = db.Column(db.String(10), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
```

在 `app/models/__init__.py` 追加：`from .trip import Trip, Leg, TripCurrency  # noqa: F401`

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_trip_model.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add app/models/ tests/
git commit -m "feat: Trip/Leg/TripCurrency 模型与城市/出行方式派生"
```

---

### Task 5: Day、Entry、EntryImage 模型

**Files:**
- Create: `app/models/day.py`
- Modify: `app/models/__init__.py`
- Create: `tests/test_day_entry_model.py`

**Interfaces:**
- Consumes: `Trip`, `City`。
- Produces:
  - `Day(id, trip_id, date, city_id, diary)`，关系 `city`, `entries`。
  - `Entry(id, day_id, category, title, description, amount, currency_code, created_at)`，关系 `images`。
  - `EntryImage(id, entry_id, path)`。
  - 常量 `CATEGORIES = ["吃饭","游玩","购物","住宿","交通"]`、`TRANSPORT_MODES = [...]`。

- [ ] **Step 1: 写失败测试**

`tests/test_day_entry_model.py`:
```python
import datetime as dt
from decimal import Decimal
from app.models.trip import Trip
from app.models.city import City
from app.models.day import Day, Entry, EntryImage

def test_day_entry_image(session):
    c = City(name="香港"); session.add(c)
    t = Trip(title="x", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,2))
    session.add(t); session.commit()
    d = Day(trip_id=t.id, date=dt.date(2026,1,1), city=c, diary="抵达")
    e = Entry(category="吃饭", title="茶餐厅", amount=Decimal("120.00"),
              currency_code="HKD")
    e.images = [EntryImage(path="uploads/a.jpg")]
    d.entries = [e]
    session.add(d); session.commit()
    assert t.days[0].entries[0].images[0].path == "uploads/a.jpg"
    assert t.days[0].city.name == "香港"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_day_entry_model.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现模型**

`app/models/day.py`:
```python
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
```

在 `app/models/__init__.py` 追加：`from .day import Day, Entry, EntryImage, CATEGORIES, TRANSPORT_MODES  # noqa: F401`

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_day_entry_model.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add app/models/ tests/
git commit -m "feat: Day/Entry/EntryImage 模型与类别枚举"
```

---

### Task 6: 汇率换算与花费统计逻辑

**Files:**
- Create: `app/services/stats.py`
- Create: `tests/test_stats.py`

**Interfaces:**
- Consumes: `Trip`, `TripCurrency`, `Day`, `Entry`，常量 `CATEGORIES`。
- Produces:
  - `to_cny(amount: Decimal, currency_code: str, rate_map: dict[str, Decimal]) -> Decimal`：人民币(CNY)直接返回；外币用 `amount / rate`，四舍五入两位。
  - `trip_stats(trip: Trip) -> dict`，结构：
    ```
    {"total_cny": Decimal,
     "by_category": {类别: Decimal, ...},        # 换算为 CNY
     "by_day": [{"date": date, "total_cny": Decimal}, ...],  # 按日期升序
     "by_currency": [{"code": str, "original": Decimal, "cny": Decimal}, ...]}
    ```

- [ ] **Step 1: 写失败测试**

`tests/test_stats.py`:
```python
import datetime as dt
from decimal import Decimal
from app.models.trip import Trip, TripCurrency
from app.models.city import City
from app.models.day import Day, Entry
from app.services import stats

def build_trip(session):
    c = City(name="冲绳"); session.add(c)
    t = Trip(title="x", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,2))
    t.currencies = [TripCurrency(currency_code="JPY", rate=Decimal("20"))]  # 1 CNY = 20 JPY
    d1 = Day(date=dt.date(2026,1,1), city=c)
    d1.entries = [
        Entry(category="吃饭", title="拉面", amount=Decimal("2000"), currency_code="JPY"),
        Entry(category="购物", title="手办", amount=Decimal("100"), currency_code="CNY"),
    ]
    d2 = Day(date=dt.date(2026,1,2), city=c)
    d2.entries = [Entry(category="吃饭", title="寿司", amount=Decimal("4000"), currency_code="JPY")]
    t.days = [d1, d2]
    session.add(t); session.commit()
    return t

def test_to_cny():
    rate_map = {"JPY": Decimal("20")}
    assert stats.to_cny(Decimal("2000"), "JPY", rate_map) == Decimal("100.00")
    assert stats.to_cny(Decimal("100"), "CNY", rate_map) == Decimal("100.00")

def test_trip_stats(session):
    t = build_trip(session)
    s = stats.trip_stats(t)
    # 2000JPY/20 + 100CNY + 4000JPY/20 = 100 + 100 + 200 = 400
    assert s["total_cny"] == Decimal("400.00")
    assert s["by_category"]["吃饭"] == Decimal("300.00")
    assert s["by_category"]["购物"] == Decimal("100.00")
    assert s["by_day"][0]["total_cny"] == Decimal("200.00")
    assert s["by_day"][1]["total_cny"] == Decimal("200.00")
    jpy = next(x for x in s["by_currency"] if x["code"] == "JPY")
    assert jpy["original"] == Decimal("6000")
    assert jpy["cny"] == Decimal("300.00")
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_stats.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现统计逻辑**

`app/services/stats.py`:
```python
from decimal import Decimal, ROUND_HALF_UP
from app.models.day import CATEGORIES

TWO = Decimal("0.01")

def to_cny(amount, currency_code, rate_map):
    amount = Decimal(amount)
    if currency_code == "CNY":
        cny = amount
    else:
        rate = Decimal(rate_map[currency_code])
        cny = amount / rate
    return cny.quantize(TWO, rounding=ROUND_HALF_UP)

def trip_stats(trip):
    rate_map = {c.currency_code: Decimal(c.rate) for c in trip.currencies}
    total = Decimal("0.00")
    by_category = {cat: Decimal("0.00") for cat in CATEGORIES}
    by_day = []
    by_currency = {}
    for day in sorted(trip.days, key=lambda d: d.date):
        day_total = Decimal("0.00")
        for e in day.entries:
            cny = to_cny(e.amount, e.currency_code, rate_map)
            total += cny
            day_total += cny
            by_category[e.category] = by_category.get(e.category, Decimal("0.00")) + cny
            cur = by_currency.setdefault(
                e.currency_code, {"code": e.currency_code,
                                  "original": Decimal("0"), "cny": Decimal("0.00")})
            cur["original"] += Decimal(e.amount)
            cur["cny"] += cny
        by_day.append({"date": day.date, "total_cny": day_total})
    return {
        "total_cny": total,
        "by_category": by_category,
        "by_day": by_day,
        "by_currency": list(by_currency.values()),
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_stats.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add app/services/ tests/
git commit -m "feat: 汇率换算与单旅程花费统计逻辑"
```

---

### Task 7: 文件上传辅助

**Files:**
- Create: `app/services/uploads.py`
- Create: `tests/test_uploads.py`

**Interfaces:**
- Produces: `save_upload(file_storage, upload_folder: str) -> str | None`：保存上传文件，返回相对路径 `uploads/<uuid>.<ext>`；空文件返回 None；只允许 png/jpg/jpeg/gif/webp。

- [ ] **Step 1: 写失败测试**

`tests/test_uploads.py`:
```python
import io, os
from werkzeug.datastructures import FileStorage
from app.services.uploads import save_upload

def test_save_upload(tmp_path):
    fs = FileStorage(stream=io.BytesIO(b"img"), filename="pic.JPG",
                     content_type="image/jpeg")
    rel = save_upload(fs, str(tmp_path))
    assert rel.startswith("uploads/")
    assert rel.endswith(".jpg")
    assert os.path.exists(os.path.join(str(tmp_path), os.path.basename(rel)))

def test_save_upload_empty_returns_none(tmp_path):
    fs = FileStorage(stream=io.BytesIO(b""), filename="")
    assert save_upload(fs, str(tmp_path)) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_uploads.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现上传辅助**

`app/services/uploads.py`:
```python
import os, uuid

ALLOWED = {"png", "jpg", "jpeg", "gif", "webp"}

def save_upload(file_storage, upload_folder):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        return None
    fname = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(upload_folder, exist_ok=True)
    file_storage.save(os.path.join(upload_folder, fname))
    return f"uploads/{fname}"
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_uploads.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add app/services/ tests/
git commit -m "feat: 图片上传保存辅助"
```

---

### Task 8: 基础模板与导航、入口脚本

**Files:**
- Create: `app/templates/base.html`
- Create: `app/static/style.css`
- Create: `app/blueprints/__init__.py`
- Create: `app/blueprints/main.py`
- Modify: `app/__init__.py`（注册蓝图、静态 uploads 路由）
- Create: `run.py`
- Create: `tests/test_main_routes.py`

**Interfaces:**
- Consumes: `create_app`。
- Produces: 蓝图 `main`，路由 `/`（重定向到旅程列表 `trips.list`）；`/uploads/<path>` 提供图片；`register_blueprints(app)`。

- [ ] **Step 1: 写失败测试**

`tests/test_main_routes.py`:
```python
def test_root_redirects_to_trips(client):
    resp = client.get("/")
    assert resp.status_code in (301, 302)
    assert "/trips" in resp.headers["Location"]
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_main_routes.py -v`
Expected: FAIL（404，无重定向）。

- [ ] **Step 3: 实现基础模板**

`app/templates/base.html`:
```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <title>{% block title %}旅游记录{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
  <nav class="topnav">
    <a href="{{ url_for('trips.list') }}">旅程</a>
    <a href="{{ url_for('trips.create') }}">创建</a>
    <a href="{{ url_for('settings.people') }}">设置</a>
  </nav>
  <main class="container">
    {% with messages = get_flashed_messages() %}
      {% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}
    {% endwith %}
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

`app/static/style.css`:
```css
body { font-family: system-ui, sans-serif; margin: 0; color: #222; }
.topnav { background:#2c3e50; padding:.8rem 1rem; }
.topnav a { color:#fff; margin-right:1rem; text-decoration:none; }
.container { max-width: 900px; margin: 1.5rem auto; padding: 0 1rem; }
.flash { background:#dff0d8; padding:.5rem; margin-bottom:1rem; }
.card { border:1px solid #ddd; border-radius:8px; padding:1rem; margin-bottom:1rem; }
.btn { display:inline-block; background:#2980b9; color:#fff; padding:.4rem .8rem;
       border:none; border-radius:4px; text-decoration:none; cursor:pointer; }
.entry { border-left:3px solid #2980b9; padding-left:.6rem; margin:.5rem 0; }
img.thumb { max-height:90px; border-radius:4px; margin:2px; }
label { display:block; margin:.5rem 0 .2rem; font-weight:600; }
input, select, textarea { width:100%; padding:.4rem; box-sizing:border-box; }
```

- [ ] **Step 4: 实现 main 蓝图与上传路由**

`app/blueprints/main.py`:
```python
from flask import Blueprint, redirect, url_for, current_app, send_from_directory

bp = Blueprint("main", __name__)

@bp.route("/")
def index():
    return redirect(url_for("trips.list"))

@bp.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
```

`app/blueprints/__init__.py`:
```python
def register_blueprints(app):
    from .main import bp as main_bp
    from .trips import bp as trips_bp
    from .settings import bp as settings_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(trips_bp)
    app.register_blueprint(settings_bp)
```

在 `app/__init__.py` 的 `db.init_app(app)` 之后、`with app.app_context()` 之前加入：
```python
    from .blueprints import register_blueprints
    register_blueprints(app)
```

`run.py`:
```python
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

> 注：本任务测试依赖 trips、settings 蓝图，下两任务创建。先创建占位空蓝图以便导入：`app/blueprints/trips.py` 含 `bp = Blueprint("trips", __name__)` 与 `list/create` 占位路由；`app/blueprints/settings.py` 含 `bp = Blueprint("settings", __name__)` 与 `people` 占位路由。占位路由返回空字符串，下个任务替换。

`app/blueprints/trips.py`(占位):
```python
from flask import Blueprint
bp = Blueprint("trips", __name__, url_prefix="/trips")

@bp.route("/")
def list(): return ""

@bp.route("/create")
def create(): return ""
```

`app/blueprints/settings.py`(占位):
```python
from flask import Blueprint
bp = Blueprint("settings", __name__, url_prefix="/settings")

@bp.route("/people")
def people(): return ""
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_main_routes.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add app/ run.py tests/
git commit -m "feat: 基础模板/导航/入口与上传路由"
```

---

### Task 9: 设置页 — 同行人与城市管理

**Files:**
- Modify: `app/blueprints/settings.py`
- Create: `app/templates/settings/people.html`
- Create: `app/templates/settings/cities.html`
- Create: `tests/test_settings.py`

**Interfaces:**
- Consumes: `Person`, `City`, `geocoding.geocode`, `save_upload`, `db`。
- Produces: 路由 `settings.people`(GET 列表/POST 新增)、`settings.cities`(GET 列表/POST 新增，POST 时自动地理编码)。

- [ ] **Step 1: 写失败测试**

`tests/test_settings.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 settings 蓝图**

`app/blueprints/settings.py`（替换占位）:
```python
from flask import (Blueprint, render_template, request, redirect,
                   url_for, current_app, flash)
from app.extensions import db
from app.models.person import Person
from app.models.city import City
from app.services.geocoding import geocode
from app.services.uploads import save_upload

bp = Blueprint("settings", __name__, url_prefix="/settings")

@bp.route("/people", methods=["GET", "POST"])
def people():
    if request.method == "POST":
        name = request.form["name"].strip()
        photo = save_upload(request.files.get("photo"),
                            current_app.config["UPLOAD_FOLDER"])
        db.session.add(Person(name=name, photo=photo))
        db.session.commit()
        flash("已添加同行人")
        return redirect(url_for("settings.people"))
    return render_template("settings/people.html",
                           people=Person.query.order_by(Person.name).all())

@bp.route("/cities", methods=["GET", "POST"])
def cities():
    if request.method == "POST":
        name = request.form["name"].strip()
        coords = geocode(name)
        lat, lon = coords if coords else (None, None)
        db.session.add(City(name=name, latitude=lat, longitude=lon,
                            country=request.form.get("country") or None))
        db.session.commit()
        flash("已添加城市" + ("" if coords else "（未找到坐标，可稍后补）"))
        return redirect(url_for("settings.cities"))
    return render_template("settings/cities.html",
                           cities=City.query.order_by(City.name).all())
```

- [ ] **Step 4: 实现模板**

`app/templates/settings/people.html`:
```html
{% extends "base.html" %}
{% block title %}同行人{% endblock %}
{% block content %}
<h1>同行人</h1>
<nav><a href="{{ url_for('settings.people') }}">同行人</a> |
     <a href="{{ url_for('settings.cities') }}">城市</a></nav>
<form method="post" enctype="multipart/form-data" class="card">
  <label>姓名</label><input name="name" required>
  <label>照片</label><input type="file" name="photo" accept="image/*">
  <button class="btn" type="submit">添加</button>
</form>
{% for p in people %}
<div class="card">
  {% if p.photo %}<img class="thumb" src="{{ url_for('main.uploads', filename=p.photo.split('/')[-1]) }}">{% endif %}
  {{ p.name }}
</div>
{% endfor %}
{% endblock %}
```

`app/templates/settings/cities.html`:
```html
{% extends "base.html" %}
{% block title %}城市{% endblock %}
{% block content %}
<h1>城市</h1>
<nav><a href="{{ url_for('settings.people') }}">同行人</a> |
     <a href="{{ url_for('settings.cities') }}">城市</a></nav>
<form method="post" class="card">
  <label>城市名</label><input name="name" required>
  <label>国家/地区（选填）</label><input name="country">
  <button class="btn" type="submit">添加（自动获取坐标）</button>
</form>
{% for c in cities %}
<div class="card">{{ c.name }}
  {% if c.latitude %}<small>({{ c.latitude }}, {{ c.longitude }})</small>{% endif %}
</div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_settings.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add app/ tests/
git commit -m "feat: 设置页同行人与城市管理（城市自动地理编码）"
```

---

### Task 10: 旅程列表与创建

**Files:**
- Modify: `app/blueprints/trips.py`
- Create: `app/templates/trips/list.html`
- Create: `app/templates/trips/form.html`
- Create: `tests/test_trips_crud.py`

**Interfaces:**
- Consumes: `Trip`, `Leg`, `TripCurrency`, `Person`, `City`, `db`, `trip_stats`, `TRANSPORT_MODES`。
- Produces: 路由 `trips.list`(GET)、`trips.create`(GET 表单/POST 创建)、`trips.detail`(GET，下个任务完善)；创建时解析多段 Leg、多币种、同行人。

- [ ] **Step 1: 写失败测试**

`tests/test_trips_crud.py`:
```python
import datetime as dt
from app.models.city import City
from app.models.trip import Trip

def seed_cities(app):
    from app.extensions import db
    with app.app_context():
        bj = City(name="北京"); hk = City(name="香港")
        db.session.add_all([bj, hk]); db.session.commit()
        return bj.id, hk.id

def test_create_trip(client, app):
    bj_id, hk_id = seed_cities(app)
    resp = client.post("/trips/create", data={
        "title": "测试之旅",
        "start_date": "2026-01-01", "end_date": "2026-01-05",
        "notes": "note",
        "leg_seq": ["1"], "leg_from": [str(bj_id)], "leg_to": [str(hk_id)],
        "leg_mode": ["飞机"],
        "cur_code": ["HKD"], "cur_rate": ["1.1"],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        t = Trip.query.filter_by(title="测试之旅").one()
        assert len(t.legs) == 1
        assert t.transport_modes == ["飞机"]
        assert t.currencies[0].currency_code == "HKD"

def test_list_shows_trip(client, app):
    seed_cities(app)
    client.post("/trips/create", data={
        "title": "展示之旅", "start_date": "2026-02-01", "end_date": "2026-02-03",
    }, follow_redirects=True)
    resp = client.get("/trips/")
    assert "展示之旅" in resp.get_data(as_text=True)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_trips_crud.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 trips 蓝图（列表+创建+detail 占位）**

`app/blueprints/trips.py`（替换占位）:
```python
import datetime as dt
from decimal import Decimal
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash)
from app.extensions import db
from app.models.trip import Trip, Leg, TripCurrency
from app.models.city import City
from app.models.person import Person
from app.models.day import TRANSPORT_MODES
from app.services.stats import trip_stats

bp = Blueprint("trips", __name__, url_prefix="/trips")

def _parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()

@bp.route("/")
def list():
    trips = Trip.query.order_by(Trip.start_date.desc()).all()
    summaries = {t.id: trip_stats(t)["total_cny"] for t in trips}
    return render_template("trips/list.html", trips=trips, summaries=summaries)

def _apply_form(trip):
    trip.title = request.form["title"].strip()
    trip.start_date = _parse_date(request.form["start_date"])
    trip.end_date = _parse_date(request.form["end_date"])
    trip.notes = request.form.get("notes") or None
    # legs
    trip.legs = []
    seqs = request.form.getlist("leg_seq")
    froms = request.form.getlist("leg_from")
    tos = request.form.getlist("leg_to")
    modes = request.form.getlist("leg_mode")
    for i in range(len(seqs)):
        if not froms[i] and not tos[i]:
            continue
        trip.legs.append(Leg(
            seq=int(seqs[i] or i + 1),
            from_city_id=int(froms[i]) if froms[i] else None,
            to_city_id=int(tos[i]) if tos[i] else None,
            transport_mode=modes[i] or None))
    # currencies
    trip.currencies = []
    for code, rate in zip(request.form.getlist("cur_code"),
                          request.form.getlist("cur_rate")):
        if code.strip():
            trip.currencies.append(TripCurrency(
                currency_code=code.strip().upper(), rate=Decimal(rate)))
    # people
    pids = [int(x) for x in request.form.getlist("people")]
    trip.people = Person.query.filter(Person.id.in_(pids)).all() if pids else []

@bp.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        trip = Trip(title="", start_date=dt.date.today(), end_date=dt.date.today())
        _apply_form(trip)
        db.session.add(trip)
        db.session.commit()
        flash("旅程已创建")
        return redirect(url_for("trips.detail", trip_id=trip.id))
    return render_template("trips/form.html", trip=None,
                           cities=City.query.order_by(City.name).all(),
                           people=Person.query.order_by(Person.name).all(),
                           modes=TRANSPORT_MODES)

@bp.route("/<int:trip_id>")
def detail(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    return render_template("trips/detail.html", trip=trip,
                           stats=trip_stats(trip))
```

- [ ] **Step 4: 实现列表与表单模板**

`app/templates/trips/list.html`:
```html
{% extends "base.html" %}
{% block title %}旅程{% endblock %}
{% block content %}
<h1>我的旅程</h1>
<a class="btn" href="{{ url_for('trips.create') }}">+ 创建旅程</a>
{% for t in trips %}
<div class="card">
  <h3><a href="{{ url_for('trips.detail', trip_id=t.id) }}">{{ t.title }}</a></h3>
  <div>{{ t.start_date }} ~ {{ t.end_date }}</div>
  <div>城市：{{ t.cities | map(attribute='name') | join(' · ') or '—' }}</div>
  <div>总花费：￥{{ summaries[t.id] }}</div>
</div>
{% else %}<p>还没有旅程，点上面创建一个。</p>{% endfor %}
{% endblock %}
```

`app/templates/trips/form.html`:
```html
{% extends "base.html" %}
{% block title %}{{ '编辑' if trip else '创建' }}旅程{% endblock %}
{% block content %}
<h1>{{ '编辑' if trip else '创建' }}旅程</h1>
<form method="post" class="card">
  <label>标题</label>
  <input name="title" required value="{{ trip.title if trip else '' }}">
  <label>开始日期</label>
  <input type="date" name="start_date" required
         value="{{ trip.start_date if trip else '' }}">
  <label>结束日期</label>
  <input type="date" name="end_date" required
         value="{{ trip.end_date if trip else '' }}">
  <label>备注</label>
  <textarea name="notes">{{ trip.notes if trip else '' }}</textarea>

  <h3>行程段（出发→到达 + 出行方式）</h3>
  <div id="legs">
    {% for leg in (trip.legs if trip else [None, None]) %}
    <div class="leg-row">
      <input type="hidden" name="leg_seq" value="{{ loop.index }}">
      <select name="leg_from">
        <option value="">出发城市</option>
        {% for c in cities %}<option value="{{ c.id }}"
          {{ 'selected' if leg and leg.from_city_id==c.id }}>{{ c.name }}</option>{% endfor %}
      </select>
      <select name="leg_to">
        <option value="">到达城市</option>
        {% for c in cities %}<option value="{{ c.id }}"
          {{ 'selected' if leg and leg.to_city_id==c.id }}>{{ c.name }}</option>{% endfor %}
      </select>
      <select name="leg_mode">
        <option value="">方式</option>
        {% for m in modes %}<option {{ 'selected' if leg and leg.transport_mode==m }}>{{ m }}</option>{% endfor %}
      </select>
    </div>
    {% endfor %}
  </div>
  <small>城市不在列表？先到「设置→城市」添加。</small>

  <h3>币种与汇率（1 人民币 = ? 外币）</h3>
  <div id="currencies">
    {% for c in (trip.currencies if trip else [None]) %}
    <div><input name="cur_code" placeholder="如 JPY"
                value="{{ c.currency_code if c else '' }}">
         <input name="cur_rate" placeholder="如 20.8"
                value="{{ c.rate if c else '' }}"></div>
    {% endfor %}
  </div>

  <h3>同行人</h3>
  {% for p in people %}
  <label style="font-weight:400">
    <input type="checkbox" name="people" value="{{ p.id }}" style="width:auto"
      {{ 'checked' if trip and p in trip.people }}> {{ p.name }}</label>
  {% endfor %}

  <p><button class="btn" type="submit">保存</button></p>
</form>
{% endblock %}
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_trips_crud.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add app/ tests/
git commit -m "feat: 旅程列表与创建（多段行程/多币种/同行人）"
```

---

### Task 11: 旅程详情 + 添加每天与记录

**Files:**
- Create: `app/templates/trips/detail.html`
- Modify: `app/blueprints/trips.py`（加 add_day、add_entry 路由）
- Create: `tests/test_day_entry_routes.py`

**Interfaces:**
- Consumes: `Day`, `Entry`, `EntryImage`, `CATEGORIES`, `save_upload`, `Trip`。
- Produces: 路由 `trips.add_day`(POST)、`trips.add_entry`(POST)；detail 模板展示按天与记录、配图。

- [ ] **Step 1: 写失败测试**

`tests/test_day_entry_routes.py`:
```python
import datetime as dt
from app.models.city import City
from app.models.trip import Trip
from app.models.day import Day, Entry

def make_trip(app):
    from app.extensions import db
    with app.app_context():
        c = City(name="香港")
        t = Trip(title="t", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,3))
        db.session.add_all([c, t]); db.session.commit()
        return t.id, c.id

def test_add_day_and_entry(client, app):
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={
        "date": "2026-01-01", "city_id": str(cid), "diary": "抵达香港"},
        follow_redirects=True)
    with app.app_context():
        day = Day.query.filter_by(trip_id=tid).one()
        did = day.id
    resp = client.post(f"/trips/{tid}/days/{did}/entries", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120",
        "currency_code": "HKD", "description": "好吃"},
        follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        e = Entry.query.filter_by(title="茶餐厅").one()
        assert str(e.amount) == "120.00" and e.category == "吃饭"
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_day_entry_routes.py -v`
Expected: FAIL。

- [ ] **Step 3: 加 add_day / add_entry 路由**

在 `app/blueprints/trips.py` 顶部 import 增补：
```python
from flask import current_app
from app.models.day import Day, Entry, EntryImage, CATEGORIES
from app.services.uploads import save_upload
```

追加路由：
```python
@bp.route("/<int:trip_id>/days", methods=["POST"])
def add_day(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    day = Day(trip_id=trip.id,
              date=_parse_date(request.form["date"]),
              city_id=int(request.form["city_id"]) if request.form.get("city_id") else None,
              diary=request.form.get("diary") or None)
    db.session.add(day); db.session.commit()
    flash("已添加一天")
    return redirect(url_for("trips.detail", trip_id=trip.id))

@bp.route("/<int:trip_id>/days/<int:day_id>/entries", methods=["POST"])
def add_entry(trip_id, day_id):
    day = Day.query.get_or_404(day_id)
    entry = Entry(day_id=day.id,
                  category=request.form["category"],
                  title=request.form["title"].strip(),
                  description=request.form.get("description") or None,
                  amount=Decimal(request.form.get("amount") or "0"),
                  currency_code=request.form.get("currency_code", "CNY").upper())
    for f in request.files.getlist("images"):
        rel = save_upload(f, current_app.config["UPLOAD_FOLDER"])
        if rel:
            entry.images.append(EntryImage(path=rel))
    db.session.add(entry); db.session.commit()
    flash("已添加记录")
    return redirect(url_for("trips.detail", trip_id=trip_id))
```

并修改 `detail` 路由传入 `CATEGORIES`：
```python
@bp.route("/<int:trip_id>")
def detail(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    return render_template("trips/detail.html", trip=trip,
                           stats=trip_stats(trip), categories=CATEGORIES)
```

- [ ] **Step 4: 实现详情模板**

`app/templates/trips/detail.html`:
```html
{% extends "base.html" %}
{% block title %}{{ trip.title }}{% endblock %}
{% block content %}
<h1>{{ trip.title }}</h1>
<p>{{ trip.start_date }} ~ {{ trip.end_date }} ·
   出行：{{ trip.transport_modes | join(' / ') or '—' }} ·
   总花费 ￥{{ stats.total_cny }}</p>
<p>同行：{{ trip.people | map(attribute='name') | join('、') or '—' }}　
   <a href="{{ url_for('trips.stats_page', trip_id=trip.id) }}">查看统计 →</a></p>
{% if trip.notes %}<p>{{ trip.notes }}</p>{% endif %}

<h2>每天记录</h2>
{% for day in trip.days %}
<div class="card">
  <h3>{{ day.date }} · {{ day.city.name if day.city else '' }}</h3>
  {% if day.diary %}<p><em>{{ day.diary }}</em></p>{% endif %}
  {% for e in day.entries %}
  <div class="entry">
    <strong>[{{ e.category }}] {{ e.title }}</strong>
    — {{ e.amount }} {{ e.currency_code }}
    {% if e.description %}<div>{{ e.description }}</div>{% endif %}
    {% for img in e.images %}
      <img class="thumb" src="{{ url_for('main.uploads', filename=img.path.split('/')[-1]) }}">
    {% endfor %}
  </div>
  {% endfor %}
  <details><summary>+ 添加记录</summary>
  <form method="post" enctype="multipart/form-data"
        action="{{ url_for('trips.add_entry', trip_id=trip.id, day_id=day.id) }}">
    <select name="category">{% for c in categories %}<option>{{ c }}</option>{% endfor %}</select>
    <input name="title" placeholder="标题" required>
    <input name="amount" placeholder="金额" type="number" step="0.01">
    <input name="currency_code" placeholder="币种 默认CNY" value="CNY">
    <textarea name="description" placeholder="描述"></textarea>
    <input type="file" name="images" accept="image/*" multiple>
    <button class="btn" type="submit">保存记录</button>
  </form></details>
</div>
{% endfor %}

<div class="card">
  <h3>+ 添加一天</h3>
  <form method="post" action="{{ url_for('trips.add_day', trip_id=trip.id) }}">
    <label>日期</label><input type="date" name="date" required>
    <label>所在城市</label>
    <select name="city_id">
      <option value="">—</option>
      {% for c in trip.cities %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}
    </select>
    <label>日记</label><textarea name="diary"></textarea>
    <button class="btn" type="submit">添加</button>
  </form>
</div>
{% endblock %}
```

> 注：`trips.stats_page` 路由在下个任务创建；本任务测试不访问统计页，模板链接此刻不会被请求，测试通过。若担心 `url_for` 构建失败，可在本任务先加占位 `stats_page`（见 Task 12 Step 3），二选一。

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_day_entry_routes.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add app/ tests/
git commit -m "feat: 旅程详情与每天/记录添加（含多图上传）"
```

---

### Task 12: 旅程统计页（饼图 + 柱状图）

**Files:**
- Modify: `app/blueprints/trips.py`（加 stats_page）
- Create: `app/templates/trips/stats.html`
- Create: `tests/test_stats_page.py`

**Interfaces:**
- Consumes: `trip_stats`, `Trip`。
- Produces: 路由 `trips.stats_page`(GET)，模板用 Chart.js 渲染按类别饼图、按天柱状图，并列出按币种汇总。

- [ ] **Step 1: 写失败测试**

`tests/test_stats_page.py`:
```python
import datetime as dt
from decimal import Decimal
from app.models.city import City
from app.models.trip import Trip, TripCurrency
from app.models.day import Day, Entry

def test_stats_page_renders(client, app):
    from app.extensions import db
    with app.app_context():
        c = City(name="冲绳")
        t = Trip(title="t", start_date=dt.date(2026,1,1), end_date=dt.date(2026,1,1))
        t.currencies=[TripCurrency(currency_code="JPY", rate=Decimal("20"))]
        d = Day(date=dt.date(2026,1,1), city=c)
        d.entries=[Entry(category="吃饭", title="拉面", amount=Decimal("2000"),
                         currency_code="JPY")]
        t.days=[d]
        db.session.add(t); db.session.commit(); tid=t.id
    resp = client.get(f"/trips/{tid}/stats")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "吃饭" in body
    assert "100" in body  # 2000/20 = 100 CNY
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_stats_page.py -v`
Expected: FAIL。

- [ ] **Step 3: 实现 stats_page 路由**

在 `app/blueprints/trips.py` 追加：
```python
@bp.route("/<int:trip_id>/stats")
def stats_page(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    s = trip_stats(trip)
    cat_labels = [k for k, v in s["by_category"].items() if v > 0]
    cat_values = [float(s["by_category"][k]) for k in cat_labels]
    day_labels = [d["date"].isoformat() for d in s["by_day"]]
    day_values = [float(d["total_cny"]) for d in s["by_day"]]
    return render_template("trips/stats.html", trip=trip, stats=s,
                           cat_labels=cat_labels, cat_values=cat_values,
                           day_labels=day_labels, day_values=day_values)
```

- [ ] **Step 4: 实现统计模板**

`app/templates/trips/stats.html`:
```html
{% extends "base.html" %}
{% block title %}{{ trip.title }} · 统计{% endblock %}
{% block content %}
<h1>{{ trip.title }} · 花费统计</h1>
<p><a href="{{ url_for('trips.detail', trip_id=trip.id) }}">← 返回详情</a></p>
<p>总花费：<strong>￥{{ stats.total_cny }}</strong></p>

<div class="card"><h3>按类别</h3><canvas id="catChart" height="160"></canvas></div>
<div class="card"><h3>按天</h3><canvas id="dayChart" height="160"></canvas></div>

<div class="card"><h3>按币种</h3>
<table>
  <tr><th>币种</th><th>原始金额</th><th>折合人民币</th></tr>
  {% for cur in stats.by_currency %}
  <tr><td>{{ cur.code }}</td><td>{{ cur.original }}</td><td>￥{{ cur.cny }}</td></tr>
  {% endfor %}
</table></div>

<script>
new Chart(document.getElementById('catChart'), {
  type: 'pie',
  data: { labels: {{ cat_labels | tojson }},
          datasets: [{ data: {{ cat_values | tojson }} }] }
});
new Chart(document.getElementById('dayChart'), {
  type: 'bar',
  data: { labels: {{ day_labels | tojson }},
          datasets: [{ label: '人民币', data: {{ day_values | tojson }} }] },
  options: { scales: { y: { beginAtZero: true } } }
});
</script>
{% endblock %}
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_stats_page.py -v`
Expected: PASS。

- [ ] **Step 6: 全量测试**

Run: `pytest -v`
Expected: 全部 PASS。

- [ ] **Step 7: 手动冒烟（可选）**

Run: `python run.py`，浏览器访问 `http://localhost:5000`，依次：设置→添加城市/同行人→创建旅程（含行程段、币种）→详情加每天与记录→看统计页图表。

- [ ] **Step 8: 提交**

```bash
git add app/ tests/
git commit -m "feat: 旅程统计页（Chart.js 饼图/柱状图/按币种）"
```

---

### Task 13: 收尾 — 更新文档与运行说明

**Files:**
- Modify: `CLAUDE.md`（填「如何运行」）
- Modify: `DECISIONS.md`（追加技术落地记录）

- [ ] **Step 1: 更新 CLAUDE.md 运行说明**

把 `如何运行` 一节替换为：
```markdown
## 如何运行

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python run.py        # 访问 http://localhost:5000
pytest -v            # 运行测试
```
数据库 `instance/travel.db` 首次启动自动创建；图片存 `uploads/`。
```

- [ ] **Step 2: 追加 DECISIONS 记录**

在 `DECISIONS.md` 末尾追加 D5：ORM 选 Flask-SQLAlchemy；地理编码用 OpenStreetMap Nominatim（免费无 key）；图表用 Chart.js CDN；金额用 Numeric 避免浮点误差。

- [ ] **Step 3: 提交**

```bash
git add CLAUDE.md DECISIONS.md
git commit -m "docs: 补充运行说明与技术落地决策(D5)"
```

---

## Self-Review

**Spec coverage（对照设计文档第 3–7 节）：**
- 数据模型 7 张表 → Task 2–5 全覆盖（City/Person/Trip/Leg/TripCurrency/Day/Entry/EntryImage）。
- 城市/出行方式由 Leg 派生、无 TripCity 表 → Task 4 `cities`/`transport_modes` 属性。
- 汇率换算 `÷rate` → Task 6 `to_cny`。
- 五类别、同天按 created_at 排序 → Task 5。
- 城市自动地理编码 → Task 2 + Task 9。
- 页面：旅程列表/详情/创建/统计/设置(同行人·城市) → Task 9–12。
- 菜单 旅程(创建/统计)·设置 → Task 8 base.html + 各页内导航。
- 统计：饼图(类别)/柱状图(天)/按币种、仅单旅程 → Task 12。
- 第二版地图、不做项（账号/分享/云端/自动汇率/全局统计）→ 未纳入计划，符合 YAGNI。

**Placeholder scan：** Task 8 与 Task 10/11 间存在「占位蓝图/占位路由」，均为有意的渐进式构建并在后续任务替换为完整实现，非计划占位。无 TODO/TBD。

**Type consistency：** `trip_stats` 返回结构在 Task 6 定义，Task 10/12 按同字段名消费（`total_cny`/`by_category`/`by_day`/`by_currency`，`by_currency` 项含 `code/original/cny`）。`save_upload(file, folder)` 签名在 Task 7 定义，Task 9/11 一致调用。`geocode(name)` 在 Task 2 定义，Task 9 一致。Leg 字段 `from_city_id/to_city_id/transport_mode/seq` 全程一致。
