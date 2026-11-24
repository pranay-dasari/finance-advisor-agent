"""RECOMMENDATION AGENT: turns the spending analysis into ranked, quantified advice.

Rules: only discretionary categories are cut (never rent or bills). The reduction
target scales with how stressed the category is (10% default, 15% if it jumped or is
near budget, 20% if it is projected to exceed budget). Ideas are ranked by rupees saved.
"""
from __future__ import annotations

from .. import tools
from ..state import AdvisorState

TIPS = {
    "Food": "Cap food-delivery orders to a set number per week and cook or pack lunch on office days.",
    "Groceries": "Plan a weekly list and buy staples in bulk instead of quick-commerce top-ups.",
    "Shopping": "Add a 24-hour wait before any non-essential purchase above ₹2,000.",
    "Travel": "Pool rides or switch short cab trips to metro or bus where possible.",
    "Entertainment": "Pause one streaming or gaming subscription and plan a fixed number of outings.",
}


def recommendation_node(state: AdvisorState) -> dict:
    trace = list(state["trace"])
    tb = tools.ToolBox("recommendation", trace)
    a = state["analysis"]
    focus, goal = state.get("focus_category"), state.get("savings_goal")
    budgets = {b["category"]: b for b in a["budget_status"]}
    change = {r["category"]: r["change_pct"] for r in a["comparison"]}

    recs = []
    for cat, tip in TIPS.items():
        if focus and cat != focus:
            continue
        spent = a["totals"].get(cat, 0.0)
        if spent <= 0:
            continue
        b = budgets.get(cat)
        pct = 20 if b and b["projected_pct"] > 100 else \
            15 if (b and b["pct_used"] >= 80) or (change.get(cat) or 0) >= 20 else 10
        saving = tb.call("estimate_savings", spent_mtd=spent, upto_day=a["upto_day"],
                         days_in_month=a["days_in_month"], reduction_pct=pct)
        label = "food delivery" if cat == "Food" else cat.lower()
        recs.append({"category": cat, "reduction_pct": pct, "monthly_saving": saving, "tip": tip,
                     "text": f"Reducing {label} expenses by {pct}% could help save approximately "
                             f"{tools.inr(round(saving, -1))} monthly."})
    recs.sort(key=lambda r: r["monthly_saving"], reverse=True)
    recs = recs[: 1 if focus else 4]

    if not focus and a["income"] and a["savings_rate"] < 20:
        target = round(a["income"] * 0.2, -2)
        recs.append({"category": "Savings", "reduction_pct": 0, "monthly_saving": 0, "tip": "",
                     "text": f"Your savings rate is {a['savings_rate']:.0f}%. Auto-transfer {tools.inr(target)} "
                             f"(20% of income) to savings on salary day, before spending starts."})

    if goal:
        total = sum(r["monthly_saving"] for r in recs)
        trace.append(f"[recommendation] goal {tools.inr(goal)}: ideas cover {total / goal * 100:.0f}%")
    trace.append(f"[recommendation] {len(recs)} idea(s) ranked by monthly saving")
    return {"recommendations": recs, "completed": state["completed"] + ["recommendation"], "trace": trace}
