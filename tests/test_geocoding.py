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
