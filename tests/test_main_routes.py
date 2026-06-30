def test_root_redirects_to_trips(client):
    resp = client.get("/")
    assert resp.status_code in (301, 302)
    assert "/trips" in resp.headers["Location"]
