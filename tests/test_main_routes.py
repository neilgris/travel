def test_root_redirects_to_daily_expense(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/expenses/"


def test_travel_renders_globe_home(client):
    resp = client.get("/travel")
    assert resp.status_code == 200
    # 地球首页从 D12 起挪到 /travel，默认入口（/）改进日常消费更常用
    assert 'id="globe"' in resp.get_data(as_text=True)
