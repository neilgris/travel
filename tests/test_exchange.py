from decimal import Decimal
from unittest.mock import patch, MagicMock
from app.services import exchange


def _fake(payload):
    fake = MagicMock()
    fake.json.return_value = payload
    fake.raise_for_status.return_value = None
    return fake


def test_fetch_rate_returns_foreign_per_cny():
    fake = _fake({"result": "success", "base_code": "CNY",
                  "rates": {"JPY": 20.83, "USD": 0.14}})
    with patch("app.services.exchange.requests.get", return_value=fake):
        assert exchange.fetch_rate("JPY") == Decimal("20.83")


def test_fetch_rate_unknown_code_returns_none():
    fake = _fake({"result": "success", "rates": {"JPY": 20.83}})
    with patch("app.services.exchange.requests.get", return_value=fake):
        assert exchange.fetch_rate("XYZ") is None


def test_fetch_rate_cny_or_empty_returns_none():
    assert exchange.fetch_rate("CNY") is None
    assert exchange.fetch_rate("") is None
    assert exchange.fetch_rate(None) is None


def test_exchange_rate_endpoint(client):
    with patch("app.blueprints.trips.fetch_rate", return_value=Decimal("20.83")):
        resp = client.get("/trips/exchange-rate?code=jpy")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["code"] == "JPY"
    assert data["rate"] == "20.83"


def test_exchange_rate_endpoint_not_found(client):
    with patch("app.blueprints.trips.fetch_rate", return_value=None):
        resp = client.get("/trips/exchange-rate?code=xyz")
    assert resp.get_json()["rate"] is None
