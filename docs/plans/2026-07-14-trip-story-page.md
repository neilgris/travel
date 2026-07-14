# 旅程故事页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给每个旅程加一个只读的「故事页」——左侧 2D 小地图 + 右侧按天滚动的游记式回放（日记、照片、当日花费与亮点）。

**Architecture:** 后端新增 `services/story.py` 组装纯数据（天内容 + 地图数据），`blueprints/trips.py` 加一条只读路由 `GET /trips/<id>/story` 渲染 `templates/trips/story.html`。前端用离线 d3 + 现有 vendor 资产画 2D 地图，IntersectionObserver 做滚动高亮，外加一个极简照片灯箱。金额换算复用 `services/stats.py` 的 `to_cny` 口径。

**Tech Stack:** Python + Flask + SQLAlchemy + Jinja2；前端 d3.min.js + topojson-client.min.js + land-50m.json（均已在 `static/vendor/`，离线）。

## Global Constraints

- **分层**：路由进 `blueprints/` 保持薄；取数/整形逻辑进 `services/`；`models/` 不动。
- **金额**：一律 `Decimal`，换算 `人民币 = 外币 ÷ 汇率`，两位四舍五入——**复用 `app.services.stats.to_cny(amount, currency_code, rate_map)`**，不另写换算。
- **图片 URL**：`DayImage.path` 形如 `uploads/trips/4/xxx.jpg`（含 `uploads/` 前缀）。经 `main.uploads` 路由服务时，filename 必须是去掉 `uploads/` 前缀后的子路径（如 `trips/4/xxx.jpg`）。用 `img.path.split('uploads/', 1)[-1]` 取，兼容旧的平铺路径。**不要**用 `.split('/')[-1]`（只取 basename，对子目录路径会 404）。
- **纯只读**：故事页不得含任何 `<form>` / 编辑 / 删除控件。
- **测试范围**：后端（service + 路由）走 TDD，`pytest`。纯 CSS/JS 无前端测试，用浏览器预览人工核对（符合项目惯例）。
- **前端资产离线**：只引用 `static/vendor/` 下已有文件，不引入新 CDN、不联网。
- **文案**：中文，句子式（与站内其它页一致）。
- **权威设计**：[docs/specs/2026-07-14-trip-story-page-design.md](../specs/2026-07-14-trip-story-page-design.md)。

## File Structure

| 文件 | 职责 | 动作 |
|------|------|------|
| `app/services/story.py` | `story_data(trip)` 组装天内容 + 地图数据 | 新建 |
| `tests/test_story.py` | service + 路由测试 | 新建 |
| `app/blueprints/trips.py` | 加 `story` 只读路由 | 改（约第 202 行后追加） |
| `app/templates/trips/story.html` | 故事页模板（服务端渲染天内容 + hero + 地图容器 + 空态） | 新建 |
| `app/templates/trips/detail.html` | 标题区加「故事页」链接 | 改（约第 30 行同行区） |
| `app/static/story.css` | 杂志风排版 + 两栏 sticky 布局 + 窄屏降级 | 新建 |
| `app/static/story-map.js` | 2D 地图渲染 + 滚动高亮 + 照片灯箱 | 新建 |

---

### Task 1: story service — 天内容与亮点

**Files:**
- Create: `app/services/story.py`
- Test: `tests/test_story.py`

**Interfaces:**
- Consumes: `app.services.stats.to_cny(amount, currency_code, rate_map)` → `Decimal`（已存在）。
- Produces: `story_data(trip) -> dict`。本任务只交付 `dict["days"]`：一个列表，与 `sorted(trip.days, key=date)` 对齐，每项：
  ```
  {
    "date": date,               # datetime.date
    "city_name": str | None,    # 无城市时 None
    "journal": str | None,      # Day.diary，空串归一为 None
    "images": [str, ...],       # 每张 = url_for 用的子路径，如 "trips/4/xxx.jpg"
    "spend_cny": Decimal,       # 当日 Entry 折算人民币合计，无消费为 Decimal("0.00")
    "highlights": [ {"category": str, "title": str, "cny": Decimal}, ... ],  # 降序前 3
  }
  ```
  `dict["map"]` 在 Task 2 补齐；本任务先返回 `"map": {}` 占位。

- [ ] **Step 1: 写失败测试**

写入 `tests/test_story.py`：

```python
import datetime as dt
from decimal import Decimal

from app.models.city import City
from app.models.trip import Trip, TripCurrency
from app.models.day import Day, Entry, DayImage
from app.services.story import story_data


def _mk_trip(session, **kw):
    t = Trip(title=kw.get("title", "行"),
             start_date=kw.get("start", dt.date(2026, 1, 1)),
             end_date=kw.get("end", dt.date(2026, 1, 3)))
    session.add(t)
    return t


def test_days_basic_content(session):
    t = _mk_trip(session)
    c = City(name="东京", latitude=35.6, longitude=139.7)
    d = Day(date=dt.date(2026, 1, 1), city=c, diary="到东京，吃拉面")
    d.images = [DayImage(path="uploads/trips/9/a.jpg"),
                DayImage(path="uploads/trips/9/b.jpg")]
    t.days = [d]
    session.add(c)
    session.commit()

    days = story_data(t)["days"]
    assert len(days) == 1
    assert days[0]["date"] == dt.date(2026, 1, 1)
    assert days[0]["city_name"] == "东京"
    assert days[0]["journal"] == "到东京，吃拉面"
    assert days[0]["images"] == ["trips/9/a.jpg", "trips/9/b.jpg"]


def test_highlights_top3_by_cny_desc(session):
    t = _mk_trip(session)
    t.currencies = [TripCurrency(currency_code="JPY", rate=Decimal("20"))]
    d = Day(date=dt.date(2026, 1, 1))
    d.entries = [
        Entry(category="吃饭", title="拉面", amount=Decimal("2000"), currency_code="JPY"),  # 100
        Entry(category="购物", title="手办", amount=Decimal("6000"), currency_code="JPY"),  # 300
        Entry(category="游玩", title="门票", amount=Decimal("1000"), currency_code="JPY"),  # 50
        Entry(category="交通", title="地铁", amount=Decimal("400"), currency_code="JPY"),   # 20
    ]
    t.days = [d]
    session.commit()

    day = story_data(t)["days"][0]
    assert day["spend_cny"] == Decimal("450.00")  # 100+300+50+20 各已按条四舍五入
    titles = [h["title"] for h in day["highlights"]]
    assert titles == ["手办", "拉面", "门票"]  # 前 3，降序
    assert day["highlights"][0]["cny"] == Decimal("300.00")


def test_day_without_entries_or_diary(session):
    t = _mk_trip(session)
    d = Day(date=dt.date(2026, 1, 2))  # 无城市、无日记、无消费、无图
    t.days = [d]
    session.commit()

    day = story_data(t)["days"][0]
    assert day["city_name"] is None
    assert day["journal"] is None
    assert day["images"] == []
    assert day["spend_cny"] == Decimal("0.00")
    assert day["highlights"] == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_story.py -v`
Expected: FAIL —「ModuleNotFoundError: No module named 'app.services.story'」。

- [ ] **Step 3: 写最小实现**

写入 `app/services/story.py`：

```python
"""旅程故事页所需的展示数据：按天的内容 + 小地图数据。

只做取数与整形，金额换算复用 services.stats.to_cny。见
docs/specs/2026-07-14-trip-story-page-design.md。
"""
from decimal import Decimal

from app.services.stats import to_cny


def _image_subpath(path):
    """DayImage.path 形如 'uploads/trips/4/x.jpg'，去掉 uploads/ 前缀供 main.uploads 用。"""
    return path.split("uploads/", 1)[-1] if "uploads/" in path else path


def _day_content(day, rate_map):
    spend = Decimal("0.00")
    entries = []
    for e in day.entries:
        cny = to_cny(e.amount, e.currency_code, rate_map)
        spend += cny
        entries.append({"category": e.category, "title": e.title, "cny": cny})
    entries.sort(key=lambda x: x["cny"], reverse=True)
    return {
        "date": day.date,
        "city_name": day.city.name if day.city else None,
        "journal": day.diary or None,
        "images": [_image_subpath(img.path) for img in day.images],
        "spend_cny": spend,
        "highlights": entries[:3],
    }


def story_data(trip):
    rate_map = {c.currency_code: Decimal(c.rate) for c in trip.currencies}
    days = [_day_content(d, rate_map)
            for d in sorted(trip.days, key=lambda d: d.date)]
    return {"days": days, "map": {}}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_story.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: 提交**

```bash
git add app/services/story.py tests/test_story.py
git commit -m "feat: 故事页 service — 按天内容与当日花费亮点(top3)"
```

---

### Task 2: story service — 地图数据

**Files:**
- Modify: `app/services/story.py`
- Test: `tests/test_story.py`

**Interfaces:**
- Consumes: Task 1 的 `story_data`、`Trip.legs`（按 seq 排序）、`Trip.days`（按 date 排序）、`City.latitude/longitude`。
- Produces: `story_data(trip)["map"]`：
  ```
  {
    "route":  [ {"from": {"lat","lng","name"}, "to": {"lat","lng","name"}}, ... ],  # Leg 按 seq，两端都有坐标才收
    "cities": [ {"lat","lng","name"}, ... ],   # 出现在 route 里的城市，去重
    "day_cities": [ {"lat","lng"} | None, ... ],  # 与 days 下标一一对齐；无城市/缺坐标为 None
  }
  ```

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_story.py`：

```python
from app.models.trip import Leg


def test_map_route_and_cities(session):
    t = _mk_trip(session)
    bj = City(name="北京", latitude=39.9, longitude=116.4)
    tk = City(name="东京", latitude=35.6, longitude=139.7)
    session.add_all([bj, tk])
    t.legs = [Leg(seq=1, from_city=bj, to_city=tk, transport_mode="飞机")]
    t.days = [Day(date=dt.date(2026, 1, 1), city=tk)]
    session.commit()

    m = story_data(t)["map"]
    assert m["route"] == [{"from": {"lat": 39.9, "lng": 116.4, "name": "北京"},
                           "to": {"lat": 35.6, "lng": 139.7, "name": "东京"}}]
    assert {c["name"] for c in m["cities"]} == {"北京", "东京"}
    assert m["day_cities"] == [{"lat": 35.6, "lng": 139.7}]


def test_map_skips_missing_coords(session):
    t = _mk_trip(session)
    bj = City(name="北京", latitude=39.9, longitude=116.4)
    ghost = City(name="无坐标城")  # 无经纬度
    session.add_all([bj, ghost])
    t.legs = [Leg(seq=1, from_city=bj, to_city=ghost, transport_mode="火车")]
    t.days = [Day(date=dt.date(2026, 1, 1), city=ghost)]
    session.commit()

    m = story_data(t)["map"]
    assert m["route"] == []                 # 有一端缺坐标 → 整段跳过
    assert m["cities"] == []
    assert m["day_cities"] == [None]        # 该天城市缺坐标 → 高亮跳过


def test_map_no_legs_only_day_cities(session):
    t = _mk_trip(session)
    tk = City(name="东京", latitude=35.6, longitude=139.7)
    session.add(tk)
    t.days = [Day(date=dt.date(2026, 1, 1), city=tk),
              Day(date=dt.date(2026, 1, 2))]  # 第二天无城市
    session.commit()

    m = story_data(t)["map"]
    assert m["route"] == []
    assert m["day_cities"] == [{"lat": 35.6, "lng": 139.7}, None]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_story.py -v`
Expected: FAIL —「KeyError: 'route'」（`map` 是空 dict）。

- [ ] **Step 3: 写最小实现**

改 `app/services/story.py`：加一个坐标辅助与地图组装，`story_data` 用它填 `map`。

```python
def _point(city):
    """城市有经纬度才算有效，否则 None。"""
    if city is None or city.latitude is None or city.longitude is None:
        return None
    return {"lat": city.latitude, "lng": city.longitude, "name": city.name}


def _map_data(trip, sorted_days):
    route, cities, seen = [], [], set()
    for leg in trip.legs:  # Trip.legs 已按 seq 排序
        frm, to = _point(leg.from_city), _point(leg.to_city)
        if frm is None or to is None:
            continue
        route.append({"from": frm, "to": to})
        for p in (frm, to):
            if p["name"] not in seen:
                seen.add(p["name"])
                cities.append(p)
    day_cities = []
    for d in sorted_days:
        p = _point(d.city)
        day_cities.append({"lat": p["lat"], "lng": p["lng"]} if p else None)
    return {"route": route, "cities": cities, "day_cities": day_cities}
```

并把 `story_data` 改成：

```python
def story_data(trip):
    rate_map = {c.currency_code: Decimal(c.rate) for c in trip.currencies}
    sorted_days = sorted(trip.days, key=lambda d: d.date)
    days = [_day_content(d, rate_map) for d in sorted_days]
    return {"days": days, "map": _map_data(trip, sorted_days)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_story.py -v`
Expected: PASS（6 passed）。

- [ ] **Step 5: 提交**

```bash
git add app/services/story.py tests/test_story.py
git commit -m "feat: 故事页 service — 地图数据(route/cities/day_cities，缺坐标降级)"
```

---

### Task 3: 路由 + 模板骨架 + 详情页入口

**Files:**
- Modify: `app/blueprints/trips.py`（加路由）
- Create: `app/templates/trips/story.html`
- Modify: `app/templates/trips/detail.html`（加链接）
- Test: `tests/test_story.py`

**Interfaces:**
- Consumes: `story_data(trip)`、`trip_distance_km(trip)`（`app.services.distance`，详情页已用）、`trip_stats(trip)`（取 `total_cny`）。
- Produces: 路由 `trips.story`（`GET /trips/<int:trip_id>/story`）。模板把 `story["map"]` 以 JSON 注入 `#story-map` 容器的 `data-map` 属性供 Task 5 的 JS 读取。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_story.py`：

```python
def test_story_route_renders(client, app):
    from app.extensions import db
    with app.app_context():
        c = City(name="东京", latitude=35.6, longitude=139.7)
        t = Trip(title="日本行", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 1))
        t.currencies = [TripCurrency(currency_code="JPY", rate=Decimal("20"))]
        d = Day(date=dt.date(2026, 1, 1), city=c, diary="抵达东京")
        d.entries = [Entry(category="吃饭", title="拉面", amount=Decimal("2000"),
                           currency_code="JPY")]
        t.days = [d]
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client.get(f"/trips/{tid}/story")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "抵达东京" in body      # 日记
    assert "拉面" in body          # 亮点条目
    assert "100" in body           # 当日花费 2000/20=100 CNY


def test_story_route_is_readonly(client, app):
    from app.extensions import db
    with app.app_context():
        t = Trip(title="t", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 1))
        t.days = [Day(date=dt.date(2026, 1, 1), diary="日记")]
        db.session.add(t)
        db.session.commit()
        tid = t.id
    body = client.get(f"/trips/{tid}/story").get_data(as_text=True)
    assert "<form" not in body     # 只读：无任何表单/编辑控件


def test_story_route_empty_when_no_days(client, app):
    from app.extensions import db
    with app.app_context():
        t = Trip(title="空行", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 1))
        db.session.add(t)
        db.session.commit()
        tid = t.id
    resp = client.get(f"/trips/{tid}/story")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "还没有记录" in body    # 空态引导语
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_story.py -k route -v`
Expected: FAIL — 404（路由不存在）。

- [ ] **Step 3a: 加路由**

在 `app/blueprints/trips.py` 顶部 import 区加：

```python
from app.services.story import story_data
```

在 `detail` 路由之后（约第 203 行、`add_day` 之前）追加：

```python
@bp.route("/<int:trip_id>/story")
def story(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    return render_template("trips/story.html", trip=trip,
                           story=story_data(trip),
                           distance_km=trip_distance_km(trip),
                           total_cny=trip_stats(trip)["total_cny"])
```

- [ ] **Step 3b: 建模板**

写入 `app/templates/trips/story.html`（服务端渲染全部天内容；地图/灯箱交给 Task 5 的 JS，此步只放容器）：

```jinja
{% extends "base.html" %}
{% block title %}{{ trip.title }} · 故事{% endblock %}
{% block main_class %}story-main{% endblock %}
{% block content %}
<link rel="stylesheet" href="{{ url_for('static', filename='story.css') }}">

<header class="story-hero">
  <h1>{{ trip.title }}</h1>
  <p class="story-meta">
    {{ trip.start_date }} ~ {{ trip.end_date }}
    {% if trip.people %}· 同行：{{ trip.people | map(attribute='name') | join('、') }}{% endif %}
    · 里程 {{ '{:,}'.format(distance_km) }} km
    · 总花费 ￥{{ total_cny }}
  </p>
  <p class="story-links">
    <a href="{{ url_for('trips.detail', trip_id=trip.id) }}">← 返回详情</a>
    <a href="{{ url_for('trips.stats_page', trip_id=trip.id) }}">查看统计 →</a>
  </p>
</header>

{% if not story.days %}
<p class="story-empty">这段旅程还没有记录。
  <a href="{{ url_for('trips.detail', trip_id=trip.id) }}">去详情页添加 →</a></p>
{% else %}
<div class="story-body">
  <aside class="story-map-col">
    <div id="story-map" data-map='{{ story.map | tojson }}'></div>
  </aside>
  <div class="story-days">
    {% for day in story.days %}
    {% set has_content = day.journal or day.images %}
    <section class="story-day {% if not has_content %}story-day-slim{% endif %}"
             data-day-index="{{ loop.index0 }}">
      <h2 class="story-day-head">
        <span class="story-day-n">Day {{ loop.index }}</span>
        {{ day.date }}{% if day.city_name %} · {{ day.city_name }}{% endif %}
      </h2>
      {% if day.journal %}<div class="story-journal">{{ day.journal | replace('\n', '<br>') | safe }}</div>{% endif %}
      {% if day.images %}
      <div class="story-photos">
        {% for src in day.images %}
        <img class="story-photo" loading="lazy"
             src="{{ url_for('main.uploads', filename=src) }}" alt="">
        {% endfor %}
      </div>
      {% endif %}
      {% if day.spend_cny > 0 %}
      <div class="story-spend">
        <span class="story-spend-total">今日 ￥{{ day.spend_cny }}</span>
        {% for h in day.highlights %}
        <span class="story-hl">{{ h.category }} · {{ h.title }} ￥{{ h.cny }}</span>
        {% endfor %}
      </div>
      {% endif %}
    </section>
    {% endfor %}
  </div>
</div>
{% endif %}
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='vendor/d3.min.js') }}"></script>
<script src="{{ url_for('static', filename='vendor/topojson-client.min.js') }}"></script>
<script src="{{ url_for('static', filename='story-map.js') }}"></script>
{% endblock %}
```

> 注：`day.journal | replace('\n','<br>') | safe` 保留日记换行。日记是本人私填内容、无外部注入源，`safe` 可接受（与站点单机私用定位一致）。

- [ ] **Step 3c: 详情页加入口**

在 `app/templates/trips/detail.html` 的同行/链接行（约第 30 行，`查看统计 →` 链接前）插入一个故事页链接：

找到：
```jinja
   <a href="{{ url_for('trips.stats_page', trip_id=trip.id) }}">查看统计 →</a>
```
改为：
```jinja
   <a href="{{ url_for('trips.story', trip_id=trip.id) }}">故事页 →</a>
   <a href="{{ url_for('trips.stats_page', trip_id=trip.id) }}">查看统计 →</a>
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_story.py -v`
Expected: PASS（9 passed）。

- [ ] **Step 5: 全量回归 + 提交**

Run: `pytest -q`
Expected: 全绿（含既有用例）。

```bash
git add app/blueprints/trips.py app/templates/trips/story.html app/templates/trips/detail.html tests/test_story.py
git commit -m "feat: 故事页只读路由与模板骨架，详情页加入口链接"
```

---

### Task 4: 杂志风样式（story.css）

**Files:**
- Create: `app/static/story.css`

**Interfaces:**
- Consumes: Task 3 模板里的类名（`story-hero`、`story-meta`、`story-links`、`story-body`、`story-map-col`、`story-days`、`story-day`、`story-day-slim`、`story-day-head`、`story-day-n`、`story-journal`、`story-photos`、`story-photo`、`story-spend`、`story-spend-total`、`story-hl`、`story-empty`）。
- Produces: 无 JS 契约；纯样式。

本任务无 pytest 测试（纯 CSS），用浏览器预览核对。

- [ ] **Step 1: 写样式**

写入 `app/static/story.css`：

```css
/* 故事页专属样式，仅 story.html 引入，不进全站 style.css。 */
.story-main { max-width: 1100px; margin: 0 auto; padding: 1.5rem; }

.story-hero { margin-bottom: 2rem; }
.story-hero h1 { font-size: 2.4rem; line-height: 1.15; margin: 0 0 .5rem; }
.story-meta { color: #666; margin: 0 0 .5rem; }
.story-links a { margin-right: 1.2rem; text-decoration: none; }

.story-empty { color: #666; font-size: 1.1rem; }

.story-body { display: grid; grid-template-columns: 38% 1fr; gap: 2rem; align-items: start; }

.story-map-col { position: sticky; top: 1rem; }
#story-map { width: 100%; aspect-ratio: 3 / 4; background: #eef2f6;
             border-radius: 10px; overflow: hidden; }
#story-map svg { width: 100%; height: 100%; display: block; }

.story-day { padding: 1.5rem 0; border-bottom: 1px solid #eee; scroll-margin-top: 1rem; }
.story-day-slim { padding: .6rem 0; color: #888; }
.story-day-head { font-size: 1.5rem; margin: 0 0 .8rem; font-weight: 600; }
.story-day-slim .story-day-head { font-size: 1.05rem; font-weight: 500; margin: 0; }
.story-day-n { color: #b8955a; margin-right: .6rem; font-variant-numeric: tabular-nums; }

.story-journal { font-family: Georgia, "Songti SC", serif; font-size: 1.12rem;
                 line-height: 1.9; color: #2a2a2a; margin-bottom: 1rem; }

.story-photos { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: 8px; margin-bottom: 1rem; }
.story-photo { width: 100%; height: 140px; object-fit: cover; border-radius: 8px;
               cursor: zoom-in; display: block; }

.story-spend { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.story-spend-total { font-weight: 600; }
.story-hl { font-size: .85rem; background: #f3f0e9; color: #6b5a3a;
            padding: 2px 10px; border-radius: 12px; }

/* 当前天在地图上高亮时，让对应城市点变色（JS 加 .is-active 到城市点）。 */
#story-map .city-dot.is-active { fill: #e8792b; }

/* 灯箱 */
.story-lightbox { position: fixed; inset: 0; background: rgba(0,0,0,.85);
                  display: none; align-items: center; justify-content: center; z-index: 100; }
.story-lightbox.open { display: flex; }
.story-lightbox img { max-width: 92vw; max-height: 92vh; border-radius: 6px; }
.story-lb-nav { position: absolute; top: 50%; transform: translateY(-50%);
                color: #fff; font-size: 3rem; cursor: pointer; user-select: none;
                padding: 0 1.5rem; background: none; border: none; }
.story-lb-prev { left: 0; } .story-lb-next { right: 0; }

@media (max-width: 720px) {
  .story-body { grid-template-columns: 1fr; }
  .story-map-col { position: sticky; top: 0; z-index: 10; }
  #story-map { aspect-ratio: 16 / 7; }
}
```

- [ ] **Step 2: 浏览器预览核对**

用 preview 工具起 dev server（`.claude/launch.json` 里的名字；若无则新建一条跑 `python run.py`，端口 8000），访问一个真实旅程的 `/trips/<id>/story`。核对：hero 大标题、两栏布局、地图容器占位灰块 sticky、日记衬线宽行高、照片网格、亮点 pill、窄屏（resize 到 mobile）降级为上下布局。此时地图容器还是空灰块（Task 5 才画），属预期。

- [ ] **Step 3: 提交**

```bash
git add app/static/story.css
git commit -m "style: 故事页杂志风排版与两栏 sticky 布局(story.css)"
```

---

### Task 5: 2D 地图 + 滚动高亮 + 照片灯箱（story-map.js）

**Files:**
- Create: `app/static/story-map.js`

**Interfaces:**
- Consumes: 全局 `d3`、`topojson`（模板已引入）；`#story-map` 容器的 `data-map`（JSON：`{route, cities, day_cities}`）；`.story-day[data-day-index]` 元素；`.story-photo` 图片；`static/vendor/land-50m.json`。
- Produces: 无对外契约（页面自执行脚本）。

本任务无 pytest 测试（纯 JS），用浏览器预览核对。

- [ ] **Step 1: 写脚本**

写入 `app/static/story-map.js`：

```javascript
/* 故事页客户端：2D 小地图(d3 正射→改用等距投影贴合旅程) + 滚动高亮 + 照片灯箱。
   离线依赖：d3、topojson、static/vendor/land-50m.json。 */
(function () {
  const mapEl = document.getElementById("story-map");
  if (mapEl) initMap(mapEl);
  initLightbox();

  function initMap(el) {
    let data;
    try { data = JSON.parse(el.dataset.map || "{}"); } catch (e) { data = {}; }
    const cities = data.cities || [];
    const route = data.route || [];
    const dayCities = data.day_cities || [];
    if (!cities.length) {
      el.innerHTML = '<p style="padding:1rem;color:#888">暂无坐标</p>';
      return;
    }

    const w = el.clientWidth || 400;
    const h = el.clientHeight || 520;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${w} ${h}`);

    // 用旅程城市点算包围盒，等距圆柱投影 fitExtent 贴合（区域旅程也看得清）。
    const feat = { type: "FeatureCollection", features: cities.map((c) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [c.lng, c.lat] } })) };
    const projection = d3.geoEquirectangular();
    const pad = 40;
    projection.fitExtent([[pad, pad], [w - pad, h - pad]], feat);
    const path = d3.geoPath(projection);

    d3.json("/static/vendor/land-50m.json").then((topo) => {
      const land = topojson.feature(topo, topo.objects.land);
      svg.insert("path", ":first-child").datum(land)
        .attr("d", path).attr("fill", "#d7dee6").attr("stroke", "#c2ccd6");
    });

    // 路线：大圆弧线。
    svg.append("g").selectAll("path.route").data(route).join("path")
      .attr("class", "route")
      .attr("d", (r) => path({ type: "LineString",
        coordinates: [[r.from.lng, r.from.lat], [r.to.lng, r.to.lat]] }))
      .attr("fill", "none").attr("stroke", "#e8792b").attr("stroke-width", 2)
      .attr("stroke-linecap", "round").attr("opacity", 0.8);

    // 城市点 + 名字。
    const g = svg.append("g");
    g.selectAll("circle.city-dot").data(cities).join("circle")
      .attr("class", "city-dot")
      .attr("data-city", (c) => c.name)
      .attr("cx", (c) => projection([c.lng, c.lat])[0])
      .attr("cy", (c) => projection([c.lng, c.lat])[1])
      .attr("r", 4).attr("fill", "#5a6472");
    g.selectAll("text.city-label").data(cities).join("text")
      .attr("class", "city-label")
      .attr("x", (c) => projection([c.lng, c.lat])[0] + 6)
      .attr("y", (c) => projection([c.lng, c.lat])[1] + 4)
      .attr("font-size", 11).attr("fill", "#333").text((c) => c.name);

    // 滚动高亮：当前天所在城市点变色放大。
    const dots = svg.selectAll("circle.city-dot");
    function highlight(name) {
      dots.classed("is-active", (c) => c.name === name)
          .attr("r", (c) => (c.name === name ? 7 : 4));
    }
    const sections = document.querySelectorAll(".story-day[data-day-index]");
    const io = new IntersectionObserver((entries) => {
      const vis = entries.filter((e) => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!vis) return;
      const idx = +vis.target.dataset.dayIndex;
      const dc = dayCities[idx];
      if (!dc) { highlight(null); return; }
      // 用坐标反查城市名（day_cities 只有 lat/lng）。
      const city = cities.find((c) => c.lat === dc.lat && c.lng === dc.lng);
      highlight(city ? city.name : null);
    }, { rootMargin: "-45% 0px -45% 0px" });
    sections.forEach((s) => io.observe(s));
  }

  function initLightbox() {
    const photos = Array.from(document.querySelectorAll(".story-photo"));
    if (!photos.length) return;
    const box = document.createElement("div");
    box.className = "story-lightbox";
    box.innerHTML =
      '<button class="story-lb-nav story-lb-prev" aria-label="上一张">‹</button>' +
      '<img alt="">' +
      '<button class="story-lb-nav story-lb-next" aria-label="下一张">›</button>';
    document.body.appendChild(box);
    const img = box.querySelector("img");
    let i = 0;
    const show = (n) => { i = (n + photos.length) % photos.length; img.src = photos[i].src; };
    photos.forEach((p, n) => p.addEventListener("click", () => { show(n); box.classList.add("open"); }));
    box.querySelector(".story-lb-prev").addEventListener("click", (e) => { e.stopPropagation(); show(i - 1); });
    box.querySelector(".story-lb-next").addEventListener("click", (e) => { e.stopPropagation(); show(i + 1); });
    box.addEventListener("click", () => box.classList.remove("open"));
    document.addEventListener("keydown", (e) => {
      if (!box.classList.contains("open")) return;
      if (e.key === "Escape") box.classList.remove("open");
      if (e.key === "ArrowLeft") show(i - 1);
      if (e.key === "ArrowRight") show(i + 1);
    });
  }
})();
```

- [ ] **Step 2: 浏览器预览核对**

起 dev server，访问真实旅程 `/trips/<id>/story`。核对：
- 地图画出陆地底图 + 橙色路线 + 城市点与名字，投影贴合本旅程范围；
- 向下滚动，当前天所在城市点变橙放大，滚到无城市的天时高亮消失；
- 点任一照片弹灯箱，左右箭头/键盘方向键切换，Esc 或点遮罩关闭；
- 找一个无 Leg 或城市缺坐标的旅程，确认地图显示「暂无坐标」或只画点，不报错；
- 打开控制台确认无 JS 报错（`read_console_messages`）。

- [ ] **Step 3: 提交**

```bash
git add app/static/story-map.js
git commit -m "feat: 故事页 2D 地图渲染、滚动高亮与照片灯箱(story-map.js)"
```

---

## 收尾：文档同步

按 CLAUDE.md「文档同步纪律」，故事页是**新上线功能**，需同步两处状态快照：

- [ ] **设计文档 spec**：在 `docs/specs/2026-06-30-travel-journal-design.md` 的「功能总览（当前已实现）」节加一条故事页说明。
- [ ] **ROADMAP.md**：把「旅程故事页」项从 `- [ ]` 勾成 `- [x]`。
- [ ] 一并提交：`git commit -m "docs: 故事页上线，同步功能总览与 ROADMAP 勾选"`

（DECISIONS.md 仅在实现中出现新取舍/踩坑时才追加，无则不动。）

---

## Self-Review 记录

- **Spec 覆盖**：第 2 节布局/每天 section/紧凑条 → Task 3 模板 + Task 4 CSS；第 3 节路由/入口 → Task 3；第 4 节 2D 地图/滚动高亮 → Task 5；第 5 节 service schema → Task 1+2；第 6 节边界（无 Leg/无坐标/无 Day/无城市）→ Task 2 测试 + Task 3 空态 + Task 5「暂无坐标」；第 7 节测试 → Task 1/2/3 用例；第 8 节不做项未纳入 ✔。
- **类型一致**：`story_data` 返回 `{days, map}` 贯穿 Task 1/2/3；`highlights` 项键 `category/title/cny`、`day_cities` 项 `{lat,lng}|None` 在 service 与 JS 两侧一致。
- **图片 URL**：service 产出去前缀子路径，模板 `url_for('main.uploads', filename=src)`，符合 Global Constraints，不复用 detail.html 的 basename 写法。
