"""SPENDING ANALYSIS AGENT: turns raw transactions into numbers and insights.

Pipeline (each step is a tool call, visible in the trace):
  get_transactions -> categorize_transactions -> monthly_totals (this month + same days of
  the previous month) -> compare_months -> detect_anomalies -> budget_status -> insights.

Months are compared like-for-like: November (month-to-date, day 24) is compared with
October days 1-24, not all of October, so a partial month never looks like a "drop".
"""
from __future__ import annotations

from .. import tools
from ..state import AdvisorState


def spending_node(state: AdvisorState) -> dict:
    trace = list(state["trace"])
    tb = tools.ToolBox("spending", trace)
    month = state["month"]
    prev = tools.previous_month(month)
    upto, dim = tools.month_window(month)

    raw = tb.call("get_transactions", account="primary")
    txns = tb.call("categorize_transactions", txns=raw)
    cur = tb.call("monthly_totals", txns=txns, month=month, upto_day=upto)
    prev_totals = tb.call("monthly_totals", txns=txns, month=prev, upto_day=upto)
    comparison = tb.call("compare_months", cur=cur, prev=prev_totals)
    anomalies = tb.call("detect_anomalies", txns=txns, month=month)
    budgets = tb.call("budget_status", totals=cur, upto_day=upto, days_in_month=dim)
    income = tb.call("income_for", txns=txns, month=month)

    total, prev_total = sum(cur.values()), sum(prev_totals.values())
    savings = income - total
    analysis = {
        "month": month, "prev_month": prev, "upto_day": upto, "days_in_month": dim,
        "totals": cur, "prev_totals": prev_totals, "comparison": comparison,
        "total_spend": total, "prev_total_spend": prev_total,
        "income": income, "savings": savings,
        "savings_rate": (savings / income * 100) if income else 0.0,
        "anomalies": anomalies, "budget_status": budgets,
    }
    analysis["insights"] = _insights(analysis)
    trace.append(f"[spending] total={tools.inr(total)} vs {tools.inr(prev_total)} same period; "
                 f"{len(anomalies)} unusual txn(s); {len(analysis['insights'])} insight(s)")
    return {"analysis": analysis, "completed": state["completed"] + ["spending"], "trace": trace}


def _insights(a: dict) -> list[str]:
    out = []
    # the "Food spending increased by 25%" style insight: material movers only
    for r in a["comparison"]:
        if r["category"] in ("Income", "Other") or r["change_pct"] is None:
            continue
        delta = r["current"] - r["previous"]
        if abs(r["change_pct"]) >= 15 and abs(delta) >= 500:
            word = "increased" if delta > 0 else "decreased"
            out.append(f"{r['category']} spending {word} by {abs(r['change_pct']):.0f}% "
                       f"compared to the same days last month ({tools.inr(r['previous'])} to {tools.inr(r['current'])})")
    for t in a["anomalies"]:
        out.append(f"Unusual {t['category']} transaction: {tools.inr(t['amount'])} at {t['description'].title()} "
                   f"on {t['date']} ({t['multiple']}x your typical {tools.inr(t['typical'])})")
    if a["income"]:
        so_far = " so far" if a["upto_day"] < a["days_in_month"] else ""
        out.append(f"Savings rate{so_far}: {a['savings_rate']:.0f}% "
                   f"({tools.inr(a['savings'])} of {tools.inr(a['income'])} income)")
    return out
