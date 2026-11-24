"""Mock retail-banking data: raw (uncategorised) transactions, budgets, and "today".

Everything is deterministic (seeded) so demos and tests are reproducible.
Real bank integration is out of scope; `get_transactions` in tools.py is the
only place that reads this module, so swapping in a real API means replacing
one function.
"""
from __future__ import annotations

import calendar
import random
from datetime import date

# The prototype's "today". Fixed so the demo output is stable.
AS_OF = date(2026, 11, 24)
MONTHS = ["2026-08", "2026-09", "2026-10", "2026-11"]  # Nov is month-to-date

BUDGETS = {  # monthly budget per category, in INR
    "Food": 7000,
    "Groceries": 7500,
    "Shopping": 6000,
    "Travel": 3000,
    "Entertainment": 2500,
    "Bills": 35000,
}

SALARY = 85000

# category -> (txns per full month, min amount, max amount, merchant descriptors)
_PROFILES = {
    "Food": (14, 180, 650, ["SWIGGY*ORDER", "ZOMATO ONLINE", "DOMINOS PIZZA", "STARBUCKS", "MCDONALDS"]),
    "Groceries": (8, 300, 1400, ["BIGBASKET", "BLINKIT", "DMART", "ZEPTO"]),
    "Shopping": (3, 700, 2800, ["AMAZON PAY", "MYNTRA", "FLIPKART"]),
    "Travel": (6, 120, 700, ["UBER TRIP", "OLA CABS", "IRCTC", "REDBUS"]),
    "Entertainment": (4, 200, 800, ["BOOKMYSHOW", "PVR CINEMAS", "SPOTIFY", "STEAM GAMES"]),
}

# (month, category) -> multiplier on amounts. This creates the story the agents find:
# food is up ~30% in November and entertainment is running hot.
_MULTIPLIERS = {("2026-11", "Food"): 1.3, ("2026-11", "Entertainment"): 1.45}

_FIXED_BILLS = [  # day, descriptor, amount
    (1, "HOUSE RENT TRANSFER", 22000),
    (5, "ACT FIBERNET", 999),
    (8, "AIRTEL POSTPAID", 599),
    (12, "BESCOM ELECTRICITY", 2400),
]

# Hand-placed anomaly so the spike detector has something real to find.
_EXTRA = [("2026-11", 14, "CROMA ELECTRONICS", 6999)]


def build_transactions(seed: int = 7) -> list[dict]:
    """Return raw transactions: id, date, description, amount, type. No category."""
    txns: list[dict] = []
    for month in MONTHS:
        year, mon = map(int, month.split("-"))
        days_in_month = calendar.monthrange(year, mon)[1]
        last_day = AS_OF.day if (year, mon) == (AS_OF.year, AS_OF.month) else days_in_month

        txns.append(_t(month, 1, "SALARY CREDIT ACME TECH", SALARY, "credit"))
        for day, desc, amt in _FIXED_BILLS:
            if day <= last_day:
                txns.append(_t(month, day, desc, amt, "debit"))

        for cat, (n_full, lo, hi, merchants) in _PROFILES.items():
            rng = random.Random(f"{seed}-{month}-{cat}")
            n = round(n_full * last_day / days_in_month)
            mult = _MULTIPLIERS.get((month, cat), 1.0)
            mid = (lo + hi) / 2
            for i in range(n):
                # evenly spaced days and +/-25% amounts: realistic but stable month to month,
                # so like-for-like comparisons show the story, not random noise
                day = min(last_day, max(1, int((i + 0.5) * last_day / n + rng.uniform(-0.8, 0.8)) + 1))
                txns.append(_t(month, day, rng.choice(merchants),
                               round(mid * rng.uniform(0.75, 1.25) * mult), "debit"))

        for m, day, desc, amt in _EXTRA:
            if m == month and day <= last_day:
                txns.append(_t(month, day, desc, amt, "debit"))

    txns.sort(key=lambda t: t["date"])
    for i, t in enumerate(txns, 1):
        t["id"] = f"TXN{i:04d}"
    return txns


def _t(month: str, day: int, desc: str, amount: float, kind: str) -> dict:
    return {"date": f"{month}-{day:02d}", "description": desc, "amount": float(amount), "type": kind}
