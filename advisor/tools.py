"""Tool layer. Plain, typed, side-effect-free functions the agents call.

Agents never touch data.py directly; they go through a `ToolBox`, which
(1) dispatches by name (so the call is a real function call, like LLM
tool-calling would be) and (2) logs every call to the reasoning trace.
"""
from __future__ import annotations

import calendar
import statistics
from typing import Callable

from . import data

DISCRETIONARY = {"Food", "Shopping", "Entertainment", "Travel", "Groceries"}

# keyword in the bank description -> spending category
MERCHANT_RULES = {
    "SWIGGY": "Food", "ZOMATO": "Food", "DOMINOS": "Food", "STARBUCKS": "Food", "MCDONALDS": "Food",
    "BIGBASKET": "Groceries", "BLINKIT": "Groceries", "DMART": "Groceries", "ZEPTO": "Groceries",
    "AMAZON": "Shopping", "MYNTRA": "Shopping", "FLIPKART": "Shopping", "CROMA": "Shopping",
    "UBER": "Travel", "OLA": "Travel", "IRCTC": "Travel", "REDBUS": "Travel",
    "BOOKMYSHOW": "Entertainment", "PVR": "Entertainment", "SPOTIFY": "Entertainment", "STEAM": "Entertainment",
    "RENT": "Bills", "FIBERNET": "Bills", "AIRTEL": "Bills", "ELECTRICITY": "Bills",
    "SALARY": "Income",
}


def inr(x: float) -> str:
    """Format as rupees with Indian digit grouping: 1234567 -> ₹12,34,567."""
    s = f"{abs(round(x)):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if x < 0 else "") + "₹" + s


# --------------------------------------------------------------------- tools
def get_transactions(account: str = "primary") -> list[dict]:
    """Fetch raw transactions for the account (mock bank API)."""
    return data.build_transactions()


def categorize_transactions(txns: list[dict]) -> list[dict]:
    """Attach a category to each transaction from merchant keywords."""
    out = []
    for t in txns:
        cat = next((c for k, c in MERCHANT_RULES.items() if k in t["description"].upper()), "Other")
        out.append({**t, "category": cat})
    return out


def month_window(month: str) -> tuple[int, int]:
    """(last_day_to_count, days_in_month). The current month is month-to-date."""
    y, m = map(int, month.split("-"))
    dim = calendar.monthrange(y, m)[1]
    upto = data.AS_OF.day if (y, m) == (data.AS_OF.year, data.AS_OF.month) else dim
    return upto, dim


def previous_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def monthly_totals(txns: list[dict], month: str, upto_day: int | None = None) -> dict[str, float]:
    """Debit totals per category for a month, optionally only up to a day of month."""
    totals: dict[str, float] = {}
    for t in txns:
        if t["type"] != "debit" or not t["date"].startswith(month):
            continue
        if upto_day is not None and int(t["date"][8:]) > upto_day:
            continue
        totals[t["category"]] = totals.get(t["category"], 0.0) + t["amount"]
    return totals


def income_for(txns: list[dict], month: str) -> float:
    return sum(t["amount"] for t in txns if t["type"] == "credit" and t["date"].startswith(month))


def compare_months(cur: dict[str, float], prev: dict[str, float]) -> list[dict]:
    """Per-category change. Callers pass like-for-like windows (same days of month)."""
    rows = []
    for cat in sorted(set(cur) | set(prev)):
        c, p = cur.get(cat, 0.0), prev.get(cat, 0.0)
        pct = ((c - p) / p * 100) if p else None
        rows.append({"category": cat, "current": c, "previous": p, "change_pct": pct})
    return sorted(rows, key=lambda r: r["current"], reverse=True)


def detect_anomalies(txns: list[dict], month: str) -> list[dict]:
    """Flag single transactions >= 3x the category's median and >= ₹2,000.

    Recurring Bills and Income are skipped; their size is expected.
    """
    by_cat: dict[str, list[float]] = {}
    for t in txns:
        if t["type"] == "debit" and t["category"] not in {"Bills", "Income", "Other"}:
            by_cat.setdefault(t["category"], []).append(t["amount"])
    medians = {c: statistics.median(v) for c, v in by_cat.items()}
    found = []
    for t in txns:
        if t["type"] != "debit" or not t["date"].startswith(month) or t["category"] not in medians:
            continue
        if t["amount"] >= 2000 and t["amount"] >= 3 * medians[t["category"]]:
            found.append({**t, "typical": medians[t["category"]],
                          "multiple": round(t["amount"] / medians[t["category"]], 1)})
    return found


def budget_status(totals: dict[str, float], upto_day: int, days_in_month: int) -> list[dict]:
    """Spend vs budget, plus a straight-line projection to month end."""
    rows = []
    for cat, budget in data.BUDGETS.items():
        spent = totals.get(cat, 0.0)
        projected = spent if cat == "Bills" else spent / upto_day * days_in_month
        rows.append({"category": cat, "spent": spent, "budget": budget,
                     "pct_used": spent / budget * 100, "projected": projected,
                     "projected_pct": projected / budget * 100})
    return rows


def estimate_savings(spent_mtd: float, upto_day: int, days_in_month: int, reduction_pct: float) -> float:
    """Monthly rupees saved if the category's full-month run rate drops by reduction_pct."""
    return spent_mtd / upto_day * days_in_month * reduction_pct / 100


REGISTRY: dict[str, Callable] = {f.__name__: f for f in [
    get_transactions, categorize_transactions, monthly_totals, income_for, compare_months,
    detect_anomalies, budget_status, estimate_savings,
]}


class ToolBox:
    """Name-based dispatch that records each call in the shared trace."""

    def __init__(self, agent: str, trace: list[str]):
        self.agent, self.trace = agent, trace

    def call(self, name: str, **kwargs):
        result = REGISTRY[name](**kwargs)
        shown = {k: (f"<{len(v)} items>" if isinstance(v, (list, dict)) else v) for k, v in kwargs.items()}
        self.trace.append(f"[{self.agent}] tool {name}({', '.join(f'{k}={v}' for k, v in shown.items())})")
        return result
