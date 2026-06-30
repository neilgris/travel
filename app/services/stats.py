from decimal import Decimal, ROUND_HALF_UP
from app.models.day import CATEGORIES

TWO = Decimal("0.01")


def to_cny(amount, currency_code, rate_map):
    amount = Decimal(amount)
    if currency_code == "CNY":
        cny = amount
    elif currency_code in rate_map:
        rate = Decimal(rate_map[currency_code])
        cny = amount / rate
    else:
        # Defensive: UI constrains entry currency to CNY + trip.currencies, so an unconfigured code should not reach here; treat as 0 rather than crash.
        cny = Decimal("0.00")
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
            # Accumulate per-entry rounded CNY so total_cny, by_category, by_day, by_currency stay mutually consistent.
            cny = to_cny(e.amount, e.currency_code, rate_map)
            total += cny
            day_total += cny
            by_category[e.category] += cny
            cur = by_currency.setdefault(
                e.currency_code, {"code": e.currency_code,
                                  "original": Decimal("0.00"), "cny": Decimal("0.00")})
            cur["original"] += Decimal(e.amount)
            cur["cny"] += cny
        by_day.append({"date": day.date, "total_cny": day_total})
    return {
        "total_cny": total,
        "by_category": by_category,
        "by_day": by_day,
        "by_currency": list(by_currency.values()),
    }
