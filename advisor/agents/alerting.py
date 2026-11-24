"""ALERTING AGENT: proactive risk detection from the spending analysis.

Severity: critical = budget already exceeded; warning = 80%+ used or projected to
exceed by month end, or a category spike; info = a single unusual transaction.
"""
from __future__ import annotations

from .. import tools
from ..state import AdvisorState

SEV_ORDER = {"critical": 0, "warning": 1, "info": 2}


def alerting_node(state: AdvisorState) -> dict:
    trace = list(state["trace"])
    a = state["analysis"]
    focus = state.get("focus_category")
    alerts = []

    for b in a["budget_status"]:
        cat, spent, budget = b["category"], b["spent"], b["budget"]
        if b["pct_used"] >= 100:
            alerts.append({"severity": "critical", "category": cat,
                           "message": f"You have exceeded your monthly {cat.lower()} budget: "
                                      f"{tools.inr(spent)} of {tools.inr(budget)}."})
        elif b["pct_used"] >= 80:
            alerts.append({"severity": "warning", "category": cat,
                           "message": f"You are nearing your monthly {cat.lower()} budget limit: "
                                      f"{tools.inr(spent)} of {tools.inr(budget)} ({b['pct_used']:.0f}%) used."})
        elif b["projected_pct"] >= 100 and a["upto_day"] < a["days_in_month"]:
            alerts.append({"severity": "warning", "category": cat,
                           "message": f"At the current pace {cat.lower()} will reach {tools.inr(b['projected'])} "
                                      f"by month end, over your {tools.inr(budget)} budget."})

    flagged = {t["category"] for t in a["anomalies"]}  # an unusual txn already explains its category
    for r in a["comparison"]:
        if r["category"] in ("Bills", "Income", "Other", *flagged) or r["change_pct"] is None:
            continue
        if r["change_pct"] >= 30 and r["current"] - r["previous"] >= 1000:
            alerts.append({"severity": "warning", "category": r["category"],
                           "message": f"{r['category']} spending spiked {r['change_pct']:.0f}% versus the same "
                                      f"days last month."})

    for t in a["anomalies"]:
        alerts.append({"severity": "info", "category": t["category"],
                       "message": f"Unusual spend: {tools.inr(t['amount'])} at {t['description'].title()} "
                                  f"on {t['date']}. Please confirm it was you."})

    if focus:
        alerts = [x for x in alerts if x["category"] == focus]
    alerts.sort(key=lambda x: SEV_ORDER[x["severity"]])
    trace.append(f"[alerting] {len(alerts)} alert(s): " + ", ".join(f"{x['severity']}:{x['category']}" for x in alerts))
    return {"alerts": alerts, "completed": state["completed"] + ["alerting"], "trace": trace}
