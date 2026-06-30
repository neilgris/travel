from decimal import Decimal, InvalidOperation
import requests

# open.er-api.com 免费、无需 key；base=CNY 时 rates[code] 即「1 人民币 = ? 外币」，
# 正好是本项目的汇率语义。
ER_API_URL = "https://open.er-api.com/v6/latest/CNY"


def fetch_rate(code):
    """查 1 人民币兑换多少外币，失败 / 未知币种 / 本币返回 None。"""
    code = (code or "").strip().upper()
    if not code or code == "CNY":
        return None
    try:
        resp = requests.get(
            ER_API_URL,
            headers={"User-Agent": "travel-journal/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None
    val = (data.get("rates") or {}).get(code)
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None
