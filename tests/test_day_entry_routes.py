import datetime as dt
from decimal import Decimal
from app.extensions import db
from app.models.city import City
from app.models.trip import Trip, TripCurrency
from app.models.day import Day, Entry, DayImage


def make_trip(app):
    from app.extensions import db
    with app.app_context():
        c = City(name="香港")
        t = Trip(title="t", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 3))
        t.currencies = [TripCurrency(currency_code="HKD", rate=Decimal("1.1"))]
        db.session.add_all([c, t])
        db.session.commit()
        return t.id, c.id


def test_add_entry_mismatched_trip_day_returns_404(client, app):
    # Create two separate trips; a day under trip B; POST entry to trip A's URL
    with app.app_context():
        c = City(name="上海")
        ta = Trip(title="旅程A", start_date=dt.date(2026, 2, 1), end_date=dt.date(2026, 2, 3))
        tb = Trip(title="旅程B", start_date=dt.date(2026, 3, 1), end_date=dt.date(2026, 3, 3))
        db.session.add_all([c, ta, tb])
        db.session.commit()
        day_b = Day(trip_id=tb.id, date=dt.date(2026, 3, 1))
        db.session.add(day_b)
        db.session.commit()
        ta_id = ta.id
        day_b_id = day_b.id
    resp = client.post(f"/trips/{ta_id}/days/{day_b_id}/entries", data={
        "category": "吃饭", "title": "测试", "amount": "10", "currency_code": "CNY",
    })
    assert resp.status_code == 404


def test_add_day_form_defaults_date_to_trip_start(client, app):
    tid, _ = make_trip(app)  # start_date = 2026-01-01
    html = client.get(f"/trips/{tid}").get_data(as_text=True)
    assert 'name="date" required value="2026-01-01"' in html


def test_add_day_form_defaults_to_day_after_last(client, app):
    tid, cid = make_trip(app)  # start_date = 2026-01-01
    client.post(f"/trips/{tid}/days", data={
        "date": "2026-01-02", "city_id": str(cid)}, follow_redirects=True)
    html = client.get(f"/trips/{tid}").get_data(as_text=True)
    # 已有最后一天 2026-01-02，下次默认应为 2026-01-03
    assert 'name="date" required value="2026-01-03"' in html


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


def test_add_day_images_attaches_to_day(client, app):
    import io
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        did = Day.query.filter_by(trip_id=tid).one().id
    resp = client.post(
        f"/trips/{tid}/days/{did}/images",
        data={"images": (io.BytesIO(b"fakejpeg"), "photo.jpg")},
        content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        imgs = DayImage.query.filter_by(day_id=did).all()
        assert len(imgs) == 1


def test_detail_renders_subdir_image_url(client, app):
    """详情页图片 URL 必须保留 uploads/ 后的子目录（D18 分目录后），否则 404。"""
    tid, cid = make_trip(app)
    with app.app_context():
        did = Day(trip_id=tid, date=dt.date(2026, 1, 1), city_id=cid)
        db.session.add(did)
        db.session.commit()
        db.session.add(DayImage(day_id=did.id, path=f"uploads/trips/{tid}/pic.jpg"))
        db.session.commit()
    body = client.get(f"/trips/{tid}").get_data(as_text=True)
    assert f"/uploads/trips/{tid}/pic.jpg" in body
    assert "/uploads/pic.jpg" not in body  # 不能塌成 basename


def test_add_day_images_ajax_returns_json(client, app):
    # 异步（fetch）上传：带 X-Requested-With 时返回新图的 id + url，供前端插进 .day-photos。
    import io
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        did = Day.query.filter_by(trip_id=tid).one().id
    resp = client.post(
        f"/trips/{tid}/days/{did}/images",
        data={"images": (io.BytesIO(b"fakejpeg"), "photo.jpg")},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert len(payload["images"]) == 1
    with app.app_context():
        img = DayImage.query.filter_by(day_id=did).one()
        assert payload["images"][0]["id"] == img.id
        assert payload["images"][0]["url"].endswith(img.path.split("uploads/", 1)[-1])
        assert "/uploads/" in payload["images"][0]["url"]


def test_add_day_images_accepts_heic_via_request(client, app):
    # 端到端：经真实请求流上传 HEIC，应成功转 JPEG（不因 EXIF 解析崩 500）。
    import io
    import pillow_heif
    from PIL import Image
    pillow_heif.register_heif_opener()
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        did = Day.query.filter_by(trip_id=tid).one().id
    img = Image.new("RGB", (4, 2), (10, 20, 30))
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation
    img.save(buf, format="HEIF", exif=exif.tobytes())
    buf.seek(0)
    resp = client.post(
        f"/trips/{tid}/days/{did}/images",
        data={"images": (buf, "photo.heic")},
        content_type="multipart/form-data",
        headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert len(payload["images"]) == 1
    assert payload["images"][0]["url"].endswith(".jpg")


def test_add_day_images_form_post_still_redirects(client, app):
    # 兜底的普通表单 POST（无 X-Requested-With）行为不变：重定向回详情页。
    import io
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        did = Day.query.filter_by(trip_id=tid).one().id
    resp = client.post(
        f"/trips/{tid}/days/{did}/images",
        data={"images": (io.BytesIO(b"fakejpeg"), "photo.jpg")},
        content_type="multipart/form-data")
    assert resp.status_code == 302


def test_add_day_images_mismatched_trip_returns_404(client, app):
    import io
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        did = Day.query.filter_by(trip_id=tid).one().id
        other = Trip(title="other", start_date=dt.date(2026, 5, 1), end_date=dt.date(2026, 5, 2))
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    resp = client.post(
        f"/trips/{other_id}/days/{did}/images",
        data={"images": (io.BytesIO(b"x"), "photo.jpg")},
        content_type="multipart/form-data")
    assert resp.status_code == 404


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


def test_edit_entry_can_move_to_another_day(client, app):
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-02", "city_id": str(cid)})
    with app.app_context():
        d1 = Day.query.filter_by(trip_id=tid, date=dt.date(2026, 1, 1)).one().id
        d2 = Day.query.filter_by(trip_id=tid, date=dt.date(2026, 1, 2)).one().id
    client.post(f"/trips/{tid}/days/{d1}/entries", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120", "currency_code": "HKD"})
    with app.app_context():
        eid = Entry.query.filter_by(title="茶餐厅").one().id
    resp = client.post(f"/trips/{tid}/days/{d1}/entries/{eid}/edit", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120",
        "currency_code": "HKD", "new_day_id": str(d2)}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Entry, eid).day_id == d2


def test_edit_entry_ignores_foreign_new_day_id(client, app):
    tid, cid = make_trip(app)
    client.post(f"/trips/{tid}/days", data={"date": "2026-01-01", "city_id": str(cid)})
    with app.app_context():
        d1 = Day.query.filter_by(trip_id=tid).one().id
        other = Trip(title="other", start_date=dt.date(2026, 5, 1), end_date=dt.date(2026, 5, 2))
        db.session.add(other)
        db.session.commit()
        other_day = Day(trip_id=other.id, date=dt.date(2026, 5, 1))
        db.session.add(other_day)
        db.session.commit()
        foreign_day_id = other_day.id
    client.post(f"/trips/{tid}/days/{d1}/entries", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120", "currency_code": "HKD"})
    with app.app_context():
        eid = Entry.query.filter_by(title="茶餐厅").one().id
    client.post(f"/trips/{tid}/days/{d1}/entries/{eid}/edit", data={
        "category": "吃饭", "title": "茶餐厅", "amount": "120",
        "currency_code": "HKD", "new_day_id": str(foreign_day_id)}, follow_redirects=True)
    with app.app_context():
        # 跨旅程的 day_id 被忽略，记录仍留在原来的天。
        assert db.session.get(Entry, eid).day_id == d1


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
