import datetime as dt
from decimal import Decimal

from app.extensions import db
from app.models.city import City
from app.models.day import Day, Entry
from app.models.trip import Trip, TripCurrency, Leg


def seed(app):
    """一趟 2026 东京 + 一趟 2025 国内，供路由测试用。"""
    with app.app_context():
        bj = City(name="北京", country="中国", latitude=39.90, longitude=116.41)
        tokyo = City(name="东京", country="日本", latitude=35.68, longitude=139.69)
        db.session.add_all([bj, tokyo])
        db.session.flush()
        t0 = Trip(title="国内游", start_date=dt.date(2025, 5, 1),
                  end_date=dt.date(2025, 5, 2))
        t0.legs = [Leg(seq=0, from_city=bj, to_city=bj, transport_mode="高铁")]
        t = Trip(title="东京之旅", start_date=dt.date(2026, 4, 1),
                 end_date=dt.date(2026, 4, 3))
        t.currencies = [TripCurrency(currency_code="JPY", rate=Decimal("20"))]
        t.legs = [Leg(seq=0, from_city=bj, to_city=tokyo, transport_mode="飞机")]
        d = Day(date=dt.date(2026, 4, 1), city=tokyo)
        d.entries = [Entry(category="吃饭", title="寿司", amount=Decimal("4000"),
                           currency_code="JPY")]
        t.days = [d]
        db.session.add_all([t0, t])
        db.session.commit()


def test_overview_renders(client, app):
    seed(app)
    resp = client.get("/insights/")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "在途天数" in body
    assert "东京之旅" in body        # 最贵旅程卡（Task 6 搬来）或里程碑
    assert "第一次出国" in body


def test_overview_empty_db(client, app):
    resp = client.get("/insights/")
    assert resp.status_code == 200
    assert "还没有旅程" in resp.get_data(as_text=True)


def test_nav_has_insights_link(client, app):
    resp = client.get("/trips/")
    assert 'href="/insights/"' in resp.get_data(as_text=True)


def test_overview_has_year_chart_and_board(client, app):
    seed(app)
    body = client.get("/insights/").get_data(as_text=True)
    assert "逐年对比" in body
    assert 'id="yearChart"' in body
    assert 'id="compareChart"' in body     # 各旅程花费对比（从列表页搬来）
    assert 'id="globalCat"' in body        # 整体消费构成环图
    assert "最贵旅程" in body


def test_list_page_is_list_only(client, app):
    seed(app)
    body = client.get("/trips/").get_data(as_text=True)
    assert "东京之旅" in body            # 列表本体还在
    assert "历史总花费" not in body      # 看板已搬走
    assert 'id="compareChart"' not in body
    assert "最贵旅程" not in body


def test_year_report_renders(client, app):
    seed(app)
    resp = client.get("/insights/2026")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "2026" in body
    assert "东京之旅" in body
    assert "新解锁" in body            # 日本是 2026 首访
    assert "寿司" in body              # 年度之最：最贵的一顿饭
    assert 'id="year-map"' in body


def test_year_report_404_for_year_without_trips(client, app):
    seed(app)
    assert client.get("/insights/2020").status_code == 404


def test_year_report_year_nav(client, app):
    seed(app)
    body = client.get("/insights/2026").get_data(as_text=True)
    assert 'href="/insights/2025"' in body     # 上一年有数据
