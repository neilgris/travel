def test_root_renders_globe_home(client):
    resp = client.get("/")
    assert resp.status_code == 200
    # 首页是 3D 地球页（D12 起，不再重定向到 /trips）
    assert 'id="globe"' in resp.get_data(as_text=True)
