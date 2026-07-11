from unittest.mock import patch, MagicMock
from app.services import geocoding

def test_geocode_returns_coords_and_country_code():
    fake = MagicMock()
    fake.json.return_value = [{"lat": "43.06", "lon": "141.35", "importance": 0.7,
                                "address": {"country_code": "jp"}}]
    fake.raise_for_status.return_value = None
    with patch("app.services.geocoding.requests.get", return_value=fake):
        assert geocoding.geocode("札幌") == (43.06, 141.35, "jp")


def test_geocode_missing_address_returns_none_code():
    fake = MagicMock()
    fake.json.return_value = [{"lat": "43.06", "lon": "141.35", "importance": 0.7}]
    fake.raise_for_status.return_value = None
    with patch("app.services.geocoding.requests.get", return_value=fake):
        assert geocoding.geocode("札幌") == (43.06, 141.35, None)


def test_geocode_low_importance_match_returns_none():
    """查不到真地名时 Nominatim 可能模糊匹配到同名商铺，importance 极低，应视为查无结果。"""
    fake = MagicMock()
    fake.json.return_value = [{"lat": "25.02", "lon": "121.53", "importance": 0.0001,
                                "class": "amenity", "type": "restaurant",
                                "address": {"country_code": "tw"}}]
    fake.raise_for_status.return_value = None
    with patch("app.services.geocoding.requests.get", return_value=fake):
        assert geocoding.geocode("米科诺斯") is None

def test_geocode_no_result_returns_none():
    fake = MagicMock()
    fake.json.return_value = []
    fake.raise_for_status.return_value = None
    with patch("app.services.geocoding.requests.get", return_value=fake):
        assert geocoding.geocode("不存在的城市xyz") is None
