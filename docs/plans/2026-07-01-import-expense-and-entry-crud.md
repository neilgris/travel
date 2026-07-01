# 记账文件导入 + Entry 编辑/删除 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在旅程详情页支持上传记账 App 导出的 `.xls` 文件批量导入消费记录（Entry），并给 Entry 补齐编辑/删除功能作为导入出错时的撤销手段。

**Architecture:** 新增 `app/services/import_expense.py` 做纯函数式的解析（读 `.xls`）与匹配（日期/分类/币种是否都能对应到该旅程现有数据）；蓝图 `trips.py` 新增 4 个路由（导入上传+自动入库、待确认页确认入库、Entry 编辑、Entry 删除），全部沿用项目已有的 `db.get_or_404` + `abort(404)` 完整性校验风格。不新增数据表、不用 session 存草稿——待确认的行通过隐藏表单字段在两次请求之间传递。

**Tech Stack:** Python + Flask + SQLAlchemy（已有）；新增 `xlrd`（解析老版 `.xls`，运行时依赖）与 `xlwt`（仅测试里现造 `.xls` fixture，用不到就不会被 import）。

## Global Constraints

- 金额一律 `Decimal`，两位小数（沿用 `stats.py` 的 `ROUND_HALF_UP` 换算，不在本次改动范围内）。
- 分层：路由只写在 `app/blueprints/trips.py`；解析/匹配这类无 HTTP 依赖的逻辑写在 `app/services/`。
- 先写失败测试，再写实现（TDD）；每个任务完成后单独 commit，message 用 `feat:`/`fix:`/`test:`/`docs:` 前缀。
- 完整性校验沿用现有 `add_entry` 的写法：路径里的 `trip_id`/`day_id` 与记录实际归属不一致时 `abort(404)`，不是级联删除/软删除。
- 不做的事（明确 YAGNI，来自 DECISIONS.md D9）：不支持 `.xlsx`，不做重复导入检测，不做"记住上次映射选择"。

---

### Task 1: 新增分类「其他消费」

**Files:**
- Modify: `app/models/day.py:4`
- Test: `tests/test_day_entry_model.py`

**Interfaces:**
- Produces: `CATEGORIES` 列表新增一个元素 `"其他消费"`，供后续所有任务（Entry 编辑表单下拉、导入分类映射）使用。

- [ ] **Step 1: 写失败测试**

在 `tests/test_day_entry_model.py` 末尾追加：

```python
def test_other_expense_is_a_valid_category():
    from app.models.day import CATEGORIES
    assert CATEGORIES == ["吃饭", "游玩", "购物", "住宿", "交通", "其他消费"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_day_entry_model.py::test_other_expense_is_a_valid_category -v`
Expected: FAIL，`assert ['吃饭', '游玩', '购物', '住宿', '交通'] == [...]`

- [ ] **Step 3: 实现**

`app/models/day.py:4` 改为：

```python
CATEGORIES = ["吃饭", "游玩", "购物", "住宿", "交通", "其他消费"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_day_entry_model.py -v`
Expected: PASS（含之前已有用例）

- [ ] **Step 5: Commit**

```bash
git add app/models/day.py tests/test_day_entry_model.py
git commit -m "feat: 分类新增「其他消费」"
```

---

### Task 2: Entry 删除

**Files:**
- Modify: `app/blueprints/trips.py`（在 `add_entry` 路由后新增 `delete_entry`）
- Modify: `app/templates/trips/detail.html:22-31`（entry 循环内加删除按钮）
- Test: `tests/test_day_entry_routes.py`

**Interfaces:**
- Consumes: `app.models.day.Day`, `app.models.day.Entry`（已存在）
- Produces: 路由 `trips.delete_entry(trip_id, day_id, entry_id)`，`POST /trips/<trip_id>/days/<day_id>/entries/<entry_id>/delete`，成功后 302 重定向到 `trips.detail`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_day_entry_routes.py` 末尾追加：

```python
def test_delete_entry_removes_it(client, app):
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        day = Day.query.filter_by(trip_id=tid).one()
        did = day.id
    client.post(f"/trips/{tid}/days/{did}/entries", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120", "currency_code": "HKD"})
    with app.app_context():
        eid = Entry.query.filter_by(title="茶餐厅").one().id
    resp = client.post(f"/trips/{tid}/days/{did}/entries/{eid}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Entry.query.filter_by(id=eid).first() is None


def test_delete_entry_mismatched_day_returns_404(client, app):
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        day = Day.query.filter_by(trip_id=tid).one()
        did = day.id
    client.post(f"/trips/{tid}/days/{did}/entries", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120", "currency_code": "HKD"})
    with app.app_context():
        eid = Entry.query.filter_by(title="茶餐厅").one().id
        other = Trip(title="other", start_date=dt.date(2026, 5, 1), end_date=dt.date(2026, 5, 2))
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    resp = client.post(f"/trips/{other_id}/days/{did}/entries/{eid}/delete")
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_day_entry_routes.py -k delete_entry -v`
Expected: FAIL，404 NOT FOUND（路由不存在）

- [ ] **Step 3: 实现路由**

在 `app/blueprints/trips.py` 的 `add_entry` 函数后追加：

```python
@bp.route("/<int:trip_id>/days/<int:day_id>/entries/<int:entry_id>/delete", methods=["POST"])
def delete_entry(trip_id, day_id, entry_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    entry = db.get_or_404(Entry, entry_id)
    if entry.day_id != day_id:
        abort(404)
    db.session.delete(entry)
    db.session.commit()
    flash("已删除记录")
    return redirect(url_for("trips.detail", trip_id=trip_id))
```

- [ ] **Step 4: 加删除按钮到模板**

`app/templates/trips/detail.html` 里 entry 循环（原第 22-31 行）改为：

```html
  {% for e in day.entries %}
  <div class="entry">
    <strong>[{{ e.category }}] {{ e.title }}</strong>
    — {{ e.amount }} {{ e.currency_code }}
    {% if e.description %}<div>{{ e.description }}</div>{% endif %}
    {% for img in e.images %}
      <img class="thumb" src="{{ url_for('main.uploads', filename=img.path.split('/')[-1]) }}">
    {% endfor %}
    <form method="post" action="{{ url_for('trips.delete_entry', trip_id=trip.id, day_id=day.id, entry_id=e.id) }}"
          style="display:inline" onsubmit="return confirm('确认删除这条记录？此操作不可恢复。');">
      <button type="submit" class="link-danger">删除</button>
    </form>
  </div>
  {% endfor %}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_day_entry_routes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/trips.py app/templates/trips/detail.html tests/test_day_entry_routes.py
git commit -m "feat: Entry 支持删除"
```

---

### Task 3: Entry 编辑

**Files:**
- Modify: `app/blueprints/trips.py`（新增 `edit_entry`）
- Modify: `app/templates/trips/detail.html`（entry 循环内加行内编辑表单，紧邻 Task 2 加的删除表单之前）
- Test: `tests/test_day_entry_routes.py`

**Interfaces:**
- Consumes: `CATEGORIES`（来自 Task 1，含"其他消费"）、`trip.currencies`
- Produces: 路由 `trips.edit_entry(trip_id, day_id, entry_id)`，`POST /trips/<trip_id>/days/<day_id>/entries/<entry_id>/edit`。编辑范围：`category`/`title`/`amount`/`currency_code`/`description`，不改 `day_id`、不改图片。

- [ ] **Step 1: 写失败测试**

在 `tests/test_day_entry_routes.py` 末尾追加：

```python
def test_edit_entry_updates_fields(client, app):
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        day = Day.query.filter_by(trip_id=tid).one()
        did = day.id
    client.post(f"/trips/{tid}/days/{did}/entries", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120", "currency_code": "HKD"})
    with app.app_context():
        eid = Entry.query.filter_by(title="茶餐厅").one().id
    resp = client.post(f"/trips/{tid}/days/{did}/entries/{eid}/edit", data={
        "category": "购物", "title": "手信店", "amount": "88.5",
        "currency_code": "CNY", "description": "买手信"}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        e = db.session.get(Entry, eid)
        assert e.category == "购物"
        assert e.title == "手信店"
        assert str(e.amount) == "88.50"
        assert e.currency_code == "CNY"
        assert e.description == "买手信"


def test_edit_entry_mismatched_day_returns_404(client, app):
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        day = Day.query.filter_by(trip_id=tid).one()
        did = day.id
    client.post(f"/trips/{tid}/days/{did}/entries", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120", "currency_code": "HKD"})
    with app.app_context():
        eid = Entry.query.filter_by(title="茶餐厅").one().id
        other = Trip(title="other", start_date=dt.date(2026, 5, 1), end_date=dt.date(2026, 5, 2))
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    resp = client.post(f"/trips/{other_id}/days/{did}/entries/{eid}/edit", data={
        "category": "购物", "title": "x", "amount": "1", "currency_code": "CNY"})
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_day_entry_routes.py -k edit_entry -v`
Expected: FAIL，404 NOT FOUND（路由不存在）

- [ ] **Step 3: 实现路由**

紧接 Task 2 的 `delete_entry` 之前插入（保持"编辑路由在删除路由之前"符合 UI 里编辑按钮在删除按钮之前的顺序，纯代码组织，无功能影响）：

```python
@bp.route("/<int:trip_id>/days/<int:day_id>/entries/<int:entry_id>/edit", methods=["POST"])
def edit_entry(trip_id, day_id, entry_id):
    day = db.get_or_404(Day, day_id)
    if day.trip_id != trip_id:
        abort(404)
    entry = db.get_or_404(Entry, entry_id)
    if entry.day_id != day_id:
        abort(404)
    entry.category = request.form["category"]
    entry.title = request.form["title"].strip()
    entry.amount = Decimal(request.form.get("amount") or "0")
    entry.currency_code = request.form.get("currency_code", "CNY").upper()
    entry.description = request.form.get("description") or None
    db.session.commit()
    flash("已更新记录")
    return redirect(url_for("trips.detail", trip_id=trip_id))
```

- [ ] **Step 4: 加行内编辑表单到模板**

`app/templates/trips/detail.html` 里 entry 循环（Task 2 之后的版本）改为：

```html
  {% for e in day.entries %}
  <div class="entry">
    <strong>[{{ e.category }}] {{ e.title }}</strong>
    — {{ e.amount }} {{ e.currency_code }}
    {% if e.description %}<div>{{ e.description }}</div>{% endif %}
    {% for img in e.images %}
      <img class="thumb" src="{{ url_for('main.uploads', filename=img.path.split('/')[-1]) }}">
    {% endfor %}
    <details>
      <summary>编辑</summary>
      <form method="post" action="{{ url_for('trips.edit_entry', trip_id=trip.id, day_id=day.id, entry_id=e.id) }}"
            class="inline-edit">
        <select name="category">
          {% for c in categories %}<option {% if c == e.category %}selected{% endif %}>{{ c }}</option>{% endfor %}
        </select>
        <input name="title" value="{{ e.title }}" required>
        <input name="amount" value="{{ e.amount }}" type="number" step="0.01">
        <select name="currency_code">
          <option value="CNY" {% if e.currency_code == "CNY" %}selected{% endif %}>人民币 (CNY)</option>
          {% for cur in trip.currencies %}
          <option value="{{ cur.currency_code }}" {% if cur.currency_code == e.currency_code %}selected{% endif %}>{{ cur.currency_code }}</option>
          {% endfor %}
        </select>
        <textarea name="description">{{ e.description or '' }}</textarea>
        <button class="btn btn-sm" type="submit">保存</button>
      </form>
    </details>
    <form method="post" action="{{ url_for('trips.delete_entry', trip_id=trip.id, day_id=day.id, entry_id=e.id) }}"
          style="display:inline" onsubmit="return confirm('确认删除这条记录？此操作不可恢复。');">
      <button type="submit" class="link-danger">删除</button>
    </form>
  </div>
  {% endfor %}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest tests/test_day_entry_routes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/blueprints/trips.py app/templates/trips/detail.html tests/test_day_entry_routes.py
git commit -m "feat: Entry 支持编辑"
```

---

### Task 4: 导入解析/匹配服务层

**Files:**
- Create: `app/services/import_expense.py`
- Create: `tests/xls_helper.py`
- Create: `tests/test_import_expense.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces:
  - `CATEGORY_MAP: dict[str, str]`（一级分类原文 → 系统分类）
  - `ACCOUNT_CURRENCY_MAP: dict[str, str]`（支出账户原文 → 币种代码）
  - `parse_rows(file_obj) -> list[dict]`，每个 dict 含 `date`(`datetime.date`)、`category_raw`(str)、`account_raw`(str)、`amount`(`Decimal`)、`title`(str)
  - `match_row(trip, row: dict) -> tuple[bool, dict]`，返回 `(matched, resolved)`；`resolved` 含 `day_id`（int 或 None）、`date`（原样透传，供未匹配行展示用）、`category`（str 或 None）、`currency_code`（str 或 None）、`amount`（Decimal）、`title`（str，已截断到 200 字符）
- Consumes: `app.models.trip.Trip`（读 `trip.days`、`trip.currencies`，均为已有关系属性）

- [ ] **Step 1: 写测试用的 xls 生成 helper**

Create `tests/xls_helper.py`:

```python
import io
import xlwt

HEADER = ["交易类型", "日期", "一级分类", "二级分类", "支出账户",
          "金额", "成员", "商家", "项目", "备注"]


def make_xls_bytes(rows, sheet_name="支出"):
    """按记账 App 导出格式生成一个内存 .xls，供测试上传/解析用。
    rows: 每项 dict，需含 date/category/account/amount/note，其余列可省略。
    """
    wb = xlwt.Workbook()
    sheet = wb.add_sheet(sheet_name)
    for c, h in enumerate(HEADER):
        sheet.write(0, c, h)
    for r, row in enumerate(rows, start=1):
        sheet.write(r, 0, "支出")
        sheet.write(r, 1, row["date"])
        sheet.write(r, 2, row["category"])
        sheet.write(r, 3, row.get("subcategory", ""))
        sheet.write(r, 4, row["account"])
        sheet.write(r, 5, row["amount"])
        sheet.write(r, 6, row.get("member", ""))
        sheet.write(r, 7, row.get("merchant", ""))
        sheet.write(r, 8, row.get("project", ""))
        sheet.write(r, 9, row["note"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 2: 写失败测试**

Create `tests/test_import_expense.py`:

```python
import datetime as dt
from decimal import Decimal
import io
from app.extensions import db
from app.models.trip import Trip, TripCurrency
from app.models.day import Day
from app.services.import_expense import parse_rows, match_row
from tests.xls_helper import make_xls_bytes


def test_parse_rows_reads_date_category_account_amount_title():
    content = make_xls_bytes([
        {"date": "2026-01-20 10:00:00", "category": "旅游餐饮费",
         "account": "现金", "amount": 19.0, "note": "南翔馒头店"},
    ])
    rows = parse_rows(io.BytesIO(content))
    assert rows == [{
        "date": dt.date(2026, 1, 20),
        "category_raw": "旅游餐饮费",
        "account_raw": "现金",
        "amount": Decimal("19.0"),
        "title": "南翔馒头店",
    }]


def _make_trip(app, currencies=None):
    with app.app_context():
        t = Trip(title="t", start_date=dt.date(2026, 1, 20), end_date=dt.date(2026, 1, 21))
        t.currencies = [TripCurrency(currency_code=code, rate=Decimal(rate))
                       for code, rate in (currencies or [])]
        db.session.add(t)
        db.session.commit()
        db.session.add(Day(trip_id=t.id, date=dt.date(2026, 1, 20)))
        db.session.commit()
        return db.session.get(Trip, t.id)


def test_match_row_all_fields_resolve(app):
    with app.app_context():
        trip = _make_trip(app)
        row = {"date": dt.date(2026, 1, 20), "category_raw": "旅游餐饮费",
               "account_raw": "现金", "amount": Decimal("19.0"), "title": "南翔馒头店"}
        matched, resolved = match_row(trip, row)
        assert matched is True
        assert resolved["category"] == "吃饭"
        assert resolved["currency_code"] == "CNY"
        assert resolved["day_id"] == trip.days[0].id


def test_match_row_unknown_category_is_unmatched(app):
    with app.app_context():
        trip = _make_trip(app)
        row = {"date": dt.date(2026, 1, 20), "category_raw": "神秘分类",
               "account_raw": "现金", "amount": Decimal("60"), "title": "x"}
        matched, resolved = match_row(trip, row)
        assert matched is False
        assert resolved["category"] is None
        assert resolved["currency_code"] == "CNY"


def test_match_row_date_outside_trip_days_is_unmatched(app):
    with app.app_context():
        trip = _make_trip(app)
        row = {"date": dt.date(2026, 1, 1), "category_raw": "旅游交通费",
               "account_raw": "现金", "amount": Decimal("60"), "title": "保险"}
        matched, resolved = match_row(trip, row)
        assert matched is False
        assert resolved["day_id"] is None
        assert resolved["category"] == "交通"


def test_match_row_undeclared_currency_is_unmatched(app):
    with app.app_context():
        trip = _make_trip(app)  # 没有声明 JPY
        row = {"date": dt.date(2026, 1, 20), "category_raw": "旅游买买买",
               "account_raw": "日元", "amount": Decimal("300"), "title": "和果子"}
        matched, resolved = match_row(trip, row)
        assert matched is False
        assert resolved["currency_code"] is None
        assert resolved["category"] == "购物"


def test_match_row_declared_foreign_currency_matches(app):
    with app.app_context():
        trip = _make_trip(app, currencies=[("JPY", "22.31")])
        row = {"date": dt.date(2026, 1, 20), "category_raw": "旅游买买买",
               "account_raw": "日元", "amount": Decimal("300"), "title": "和果子"}
        matched, resolved = match_row(trip, row)
        assert matched is True
        assert resolved["currency_code"] == "JPY"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `pytest tests/test_import_expense.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.import_expense'`（以及 `xlwt`/`xlrd` 未安装的话会先报 `ModuleNotFoundError: No module named 'xlwt'`）

- [ ] **Step 4: 加依赖**

`requirements.txt` 追加两行：

```
xlrd>=2.0
xlwt>=1.3
```

Run: `pip install -r requirements.txt`

- [ ] **Step 5: 实现服务**

Create `app/services/import_expense.py`:

```python
import datetime as dt
from decimal import Decimal
import xlrd

CATEGORY_MAP = {
    "旅游餐饮费": "吃饭",
    "旅游买买买": "购物",
    "旅游娱乐费": "游玩",
    "旅游交通费": "交通",
    "旅游住宿费": "住宿",
    "其他消费": "其他消费",
}

ACCOUNT_CURRENCY_MAP = {
    "现金": "CNY",
    "港币": "HKD",
    "美元": "USD",
    "日元": "JPY",
}


def parse_rows(file_obj):
    """读取记账 App 导出的 .xls（第一个 sheet），返回原始行列表（不做匹配判断）。
    file_obj: 任意有 .read() 的文件对象（Flask FileStorage 或 io.BytesIO）。
    """
    wb = xlrd.open_workbook(file_contents=file_obj.read())
    sheet = wb.sheet_by_index(0)
    rows = []
    for r in range(1, sheet.nrows):
        values = sheet.row_values(r)
        date_raw = str(values[1]).strip()
        if not date_raw:
            continue
        date = dt.datetime.strptime(date_raw.split(" ")[0], "%Y-%m-%d").date()
        rows.append({
            "date": date,
            "category_raw": str(values[2]).strip(),
            "account_raw": str(values[4]).strip(),
            "amount": Decimal(str(values[5])),
            "title": str(values[9]).strip()[:200],
        })
    return rows


def match_row(trip, row):
    """把一行原始数据匹配到 Entry 所需字段。
    返回 (matched, resolved)；resolved 里已解析对的字段给具体值，
    没对上的字段为 None，供待确认页面渲染对应的下拉框。
    """
    day = next((d for d in trip.days if d.date == row["date"]), None)
    category = CATEGORY_MAP.get(row["category_raw"])
    currency_code = ACCOUNT_CURRENCY_MAP.get(row["account_raw"])
    if currency_code and currency_code != "CNY":
        declared = {c.currency_code for c in trip.currencies}
        if currency_code not in declared:
            currency_code = None
    matched = day is not None and category is not None and currency_code is not None
    return matched, {
        "day_id": day.id if day else None,
        "date": row["date"],
        "category": category,
        "currency_code": currency_code,
        "amount": row["amount"],
        "title": row["title"],
    }
```

- [ ] **Step 6: 跑测试确认通过**

Run: `pytest tests/test_import_expense.py -v`
Expected: PASS，6 项全过

- [ ] **Step 7: Commit**

```bash
git add app/services/import_expense.py tests/xls_helper.py tests/test_import_expense.py requirements.txt
git commit -m "feat: 新增记账文件解析/匹配服务"
```

---

### Task 5: 导入路由与页面

**Files:**
- Modify: `app/blueprints/trips.py`（新增 imports + 3 个路由：`import_expenses`、`import_confirm`）
- Modify: `app/templates/trips/detail.html`（顶部操作行加"导入记账文件"链接）
- Create: `app/templates/trips/import.html`
- Create: `app/templates/trips/import_review.html`
- Test: `tests/test_import_routes.py`

**Interfaces:**
- Consumes: `app.services.import_expense.parse_rows`、`match_row`（Task 4）；`CATEGORIES`（Task 1）
- Produces: 路由 `trips.import_expenses(trip_id)`（`GET`/`POST /trips/<trip_id>/import`）、`trips.import_confirm(trip_id)`（`POST /trips/<trip_id>/import/confirm`）

- [ ] **Step 1: 写失败测试**

Create `tests/test_import_routes.py`:

```python
import datetime as dt
from decimal import Decimal
import io
from app.extensions import db
from app.models.trip import Trip, TripCurrency
from app.models.city import City
from app.models.day import Day, Entry
from tests.xls_helper import make_xls_bytes


def make_trip_with_days(app):
    with app.app_context():
        c = City(name="香港")
        t = Trip(title="202601", start_date=dt.date(2026, 1, 20), end_date=dt.date(2026, 1, 21))
        t.currencies = [TripCurrency(currency_code="HKD", rate=Decimal("1.12"))]
        db.session.add_all([c, t])
        db.session.commit()
        db.session.add_all([
            Day(trip_id=t.id, date=dt.date(2026, 1, 20), city_id=c.id),
            Day(trip_id=t.id, date=dt.date(2026, 1, 21), city_id=c.id),
        ])
        db.session.commit()
        return t.id


def test_import_auto_creates_matched_entry(client, app):
    tid = make_trip_with_days(app)
    content = make_xls_bytes([
        {"date": "2026-01-20 10:00:00", "category": "旅游餐饮费",
         "account": "现金", "amount": 19.0, "note": "南翔馒头店"},
    ])
    resp = client.post(f"/trips/{tid}/import",
                       data={"file": (io.BytesIO(content), "bill.xls")},
                       content_type="multipart/form-data",
                       follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        e = Entry.query.filter_by(title="南翔馒头店").one()
        assert e.category == "吃饭"
        assert e.currency_code == "CNY"
        assert str(e.amount) == "19.00"


def test_import_shows_unmatched_row_and_does_not_create_entry(client, app):
    tid = make_trip_with_days(app)
    content = make_xls_bytes([
        {"date": "2026-01-01 10:00:00", "category": "旅游交通费",
         "account": "现金", "amount": 60.0, "note": "提前买的保险"},
    ])
    resp = client.post(f"/trips/{tid}/import",
                       data={"file": (io.BytesIO(content), "bill.xls")},
                       content_type="multipart/form-data")
    assert resp.status_code == 200
    assert "提前买的保险" in resp.get_data(as_text=True)
    with app.app_context():
        assert Entry.query.filter_by(title="提前买的保险").count() == 0


def test_import_confirm_creates_entry_for_unmatched_row(client, app):
    tid = make_trip_with_days(app)
    with app.app_context():
        day_id = Day.query.filter_by(trip_id=tid, date=dt.date(2026, 1, 20)).one().id
    resp = client.post(f"/trips/{tid}/import/confirm", data={
        "title": "提前买的保险", "amount": "60.0",
        "day_id": str(day_id), "category": "交通", "currency_code": "CNY",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        e = Entry.query.filter_by(title="提前买的保险").one()
        assert e.category == "交通"
        assert e.day_id == day_id


def test_import_confirm_skips_incomplete_row(client, app):
    tid = make_trip_with_days(app)
    resp = client.post(f"/trips/{tid}/import/confirm", data={
        "title": "没选日期的记录", "amount": "10.0",
        "day_id": "", "category": "交通", "currency_code": "CNY",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Entry.query.filter_by(title="没选日期的记录").count() == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_import_routes.py -v`
Expected: FAIL，404（路由不存在）

- [ ] **Step 3: 实现路由**

`app/blueprints/trips.py` 顶部 import 追加：

```python
from app.services.import_expense import parse_rows, match_row
```

在 `stats_page` 函数后追加：

```python
@bp.route("/<int:trip_id>/import", methods=["GET", "POST"])
def import_expenses(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("请选择要上传的 .xls 文件")
            return redirect(url_for("trips.import_expenses", trip_id=trip.id))
        rows = parse_rows(file)
        unmatched = []
        matched_count = 0
        for row in rows:
            matched, resolved = match_row(trip, row)
            if matched:
                db.session.add(Entry(day_id=resolved["day_id"], category=resolved["category"],
                                     title=resolved["title"], amount=resolved["amount"],
                                     currency_code=resolved["currency_code"]))
                matched_count += 1
            else:
                unmatched.append(resolved)
        db.session.commit()
        msg = f"自动导入 {matched_count} 条"
        if unmatched:
            msg += f"，{len(unmatched)} 条待确认"
        flash(msg)
        if unmatched:
            days = sorted(trip.days, key=lambda d: d.date)
            return render_template("trips/import_review.html", trip=trip,
                                   unmatched=unmatched, categories=CATEGORIES, days=days)
        return redirect(url_for("trips.detail", trip_id=trip.id))
    return render_template("trips/import.html", trip=trip)


@bp.route("/<int:trip_id>/import/confirm", methods=["POST"])
def import_confirm(trip_id):
    trip = db.get_or_404(Trip, trip_id)
    valid_day_ids = {d.id for d in trip.days}
    valid_currencies = {"CNY"} | {c.currency_code for c in trip.currencies}
    titles = request.form.getlist("title")
    amounts = request.form.getlist("amount")
    day_ids = request.form.getlist("day_id")
    categories_in = request.form.getlist("category")
    currencies_in = request.form.getlist("currency_code")
    count = 0
    for i in range(len(titles)):
        day_id = int(day_ids[i]) if day_ids[i] else None
        category = categories_in[i]
        currency_code = currencies_in[i]
        if day_id not in valid_day_ids or category not in CATEGORIES or currency_code not in valid_currencies:
            continue
        db.session.add(Entry(day_id=day_id, category=category,
                             title=titles[i][:200], amount=Decimal(amounts[i]),
                             currency_code=currency_code))
        count += 1
    db.session.commit()
    flash(f"已确认导入 {count} 条")
    return redirect(url_for("trips.detail", trip_id=trip.id))
```

- [ ] **Step 4: 上传页模板**

Create `app/templates/trips/import.html`:

```html
{% extends "base.html" %}
{% block title %}导入记账文件 · {{ trip.title }}{% endblock %}
{% block content %}
<h1>导入记账文件</h1>
<p><a href="{{ url_for('trips.detail', trip_id=trip.id) }}">← 返回旅程详情</a></p>
<form method="post" enctype="multipart/form-data" class="card">
  <label>选择 .xls 文件</label>
  <input type="file" name="file" accept=".xls" required>
  <button class="btn" type="submit">上传并导入</button>
</form>
{% endblock %}
```

- [ ] **Step 5: 待确认页模板**

Create `app/templates/trips/import_review.html`:

```html
{% extends "base.html" %}
{% block title %}导入待确认 · {{ trip.title }}{% endblock %}
{% block content %}
<h1>导入待确认</h1>
<p>以下记录部分字段没能自动匹配，请手动选择后确认导入。</p>
<form method="post" action="{{ url_for('trips.import_confirm', trip_id=trip.id) }}">
{% for row in unmatched %}
<div class="card">
  <p>{{ row.date }} · {{ row.title }} · {{ row.amount }}</p>
  <input type="hidden" name="title" value="{{ row.title }}">
  <input type="hidden" name="amount" value="{{ row.amount }}">
  {% if row.day_id %}
  <input type="hidden" name="day_id" value="{{ row.day_id }}">
  {% else %}
  <select name="day_id">
    <option value="">选择日期</option>
    {% for d in days %}<option value="{{ d.id }}">{{ d.date }}</option>{% endfor %}
  </select>
  {% endif %}
  {% if row.category %}
  <input type="hidden" name="category" value="{{ row.category }}">
  {% else %}
  <select name="category">
    <option value="">选择分类</option>
    {% for c in categories %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
  </select>
  {% endif %}
  {% if row.currency_code %}
  <input type="hidden" name="currency_code" value="{{ row.currency_code }}">
  {% else %}
  <select name="currency_code">
    <option value="CNY">人民币 (CNY)</option>
    {% for cur in trip.currencies %}
    <option value="{{ cur.currency_code }}">{{ cur.currency_code }}</option>
    {% endfor %}
  </select>
  {% endif %}
</div>
{% endfor %}
<button class="btn" type="submit">确认导入</button>
</form>
{% endblock %}
```

- [ ] **Step 6: 旅程详情页加入口链接**

`app/templates/trips/detail.html` 第 8-14 行（同行人/统计/编辑/删除那一段）里，在"查看统计"链接后加一行：

```html
<p>同行：{{ trip.people | map(attribute='name') | join('、') or '—' }}
   <a href="{{ url_for('trips.stats_page', trip_id=trip.id) }}">查看统计 →</a>
   <a href="{{ url_for('trips.import_expenses', trip_id=trip.id) }}">导入记账文件</a>
   <a href="{{ url_for('trips.edit', trip_id=trip.id) }}">编辑旅程</a>
   <form method="post" action="{{ url_for('trips.delete', trip_id=trip.id) }}"
         style="display:inline" onsubmit="return confirm('确认删除「{{ trip.title }}」？此操作不可恢复。');">
     <button type="submit" class="link-danger">删除旅程</button>
   </form></p>
```

- [ ] **Step 7: 跑测试确认通过**

Run: `pytest tests/test_import_routes.py -v`
Expected: PASS，4 项全过

Run: `pytest -v`
Expected: 全项目测试通过（含 Task 1-4 新增的用例）

- [ ] **Step 8: Commit**

```bash
git add app/blueprints/trips.py app/templates/trips/import.html app/templates/trips/import_review.html app/templates/trips/detail.html tests/test_import_routes.py
git commit -m "feat: 旅程详情页支持导入记账 .xls 文件"
```

---

### Task 6: 文档同步

**Files:**
- Modify: `CLAUDE.md`（目录结构里 `services/` 一节新增 `import_expense.py` 说明）

**Interfaces:** 无（纯文档）

- [ ] **Step 1: 更新 CLAUDE.md 目录结构**

`CLAUDE.md` 第 56-60 行现状：

```
├── services/          业务逻辑（无 HTTP，可独立测试）
│   ├── geocoding.py   城市坐标地理编码（Nominatim）
│   ├── exchange.py    实时汇率查询（open.er-api.com）
│   ├── stats.py       花费换算与单旅程统计
│   └── uploads.py     图片上传保存
```

改为：

```
├── services/          业务逻辑（无 HTTP，可独立测试）
│   ├── geocoding.py   城市坐标地理编码（Nominatim）
│   ├── exchange.py    实时汇率查询（open.er-api.com）
│   ├── stats.py       花费换算与单旅程统计
│   ├── uploads.py     图片上传保存
│   └── import_expense.py  记账 .xls 解析与匹配（导入用）
```

（即把 `uploads.py` 那行的 `└──` 改成 `├──`，`import_expense.py` 作为新的最后一项用 `└──`。）

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: 目录结构补充 import_expense.py"
```

---

## Self-Review Notes

- **Spec coverage**：3.4 节四条规则（日期/分类/币种匹配、备注→标题、二段式入库、不去重不支持 xlsx）分别对应 Task 4（映射表+match_row）、Task 5（自动入库+待确认+confirm）；D9 的 Entry 编辑/删除对应 Task 2/3；「其他消费」分类对应 Task 1。全部覆盖。
- **Placeholder scan**：已通读，无 TBD/"类似 Task N"/无码步骤。
- **Type consistency**：`match_row` 返回的 `resolved` 字段名（`day_id`/`category`/`currency_code`/`amount`/`title`/`date`）在 Task 4 测试、Task 5 路由、Task 5 模板三处保持一致；`CATEGORIES` 在 Task 1/3/5 引用一致。
