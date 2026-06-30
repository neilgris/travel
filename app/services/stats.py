from decimal import Decimal, ROUND_HALF_UP
from app.models.day import CATEGORIES

TWO = Decimal("0.01")


def to_cny(amount, currency_code, rate_map):
    amount = Decimal(amount)
    if currency_code == "CNY":
        cny = amount
    else:
        rate = Decimal(rate_map[currency_code])
        cny = amount / rate
    return cny.quantize(TWO, rounding=ROUND_HALF_UP)


def trip_stats(trip):
    rate_map = {c.currency_code: Decimal(c.rate) for c in trip.currencies}
    total = Decimal("0.00")
    by_category = {cat: Decimal("0.00") for cat in CATEGORIES}
    by_day = []
    by_currency = {}
    for day in sorted(trip.days, key=lambda d: d.date):
        day_total = Decimal("0.00")
        for e in day.entries:
            cny = to_cny(e.amount, e.currency_code, rate_map)
            total += cny
            day_total += cny
            by_category[e.category] = by_category.get(e.category, Decimal("0.00")) + cny
            cur = by_currency.setdefault(
                e.currency_code, {"code": e.currency_code,
                                  "original": Decimal("0"), "cny": Decimal("0.00")})
            cur["original"] += Decimal(e.amount)
            cur["cny"] += cny
        by_day.append({"date": day.date, "total_cny": day_total})
    return {
        "total_cny": total,
        "by_category": by_category,
        "by_day": by_day,
        "by_currency": list(by_currency.values()),
    }
