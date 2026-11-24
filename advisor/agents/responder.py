"""RESPONDER: merges every specialist's output into the final reply and updates memory.

With an LLM, it phrases the answer from a strict facts bundle (it may not invent numbers).
Without one, a deterministic template produces the same content.
"""
from __future__ import annotations

import calendar
import json

from .. import tools
from ..state import AdvisorState

HELP = ("Hi! I'm your personal finance advisor. Ask me things like:\n"
        "  - How can I improve my monthly savings?\n"
        "  - Show my spending breakdown\n"
        "  - Any budget alerts?\n"
        "  - Why is my food spending high? / How is my overall financial health?")


def _month_label(a: dict) -> str:
    y, m = map(int, a["month"].split("-"))
    rng = f"1-{a['upto_day']}" if a["upto_day"] < a["days_in_month"] else "full month"
    return f"{calendar.month_name[m]} {y} ({rng})"


def _spending_section(state: AdvisorState) -> str:
    a, focus = state["analysis"], state.get("focus_category")
    lines = [f"Spending, {_month_label(a)}"]
    if focus:
        r = next((x for x in a["comparison"] if x["category"] == focus), None)
        if r:
            ch = f" ({r['change_pct']:+.0f}% vs same days last month)" if r["change_pct"] is not None else ""
            lines.append(f"  {focus}: {tools.inr(r['current'])}{ch}")
    else:
        for r in a["comparison"]:
            ch = f"  ({r['change_pct']:+.0f}%)" if r["change_pct"] is not None else ""
            lines.append(f"  {r['category']:<14}{tools.inr(r['current']):>10}{ch}")
        chg = ((a["total_spend"] - a["prev_total_spend"]) / a["prev_total_spend"] * 100) if a["prev_total_spend"] else 0
        lines.append(f"  {'Total':<14}{tools.inr(a['total_spend']):>10}  ({chg:+.0f}% vs same days last month)")
    lines += [f"  - {i}" for i in a["insights"] if not focus or focus in i or "Savings rate" in i]
    return "\n".join(lines)


def _template(state: AdvisorState) -> str:
    if state["intent"] == "smalltalk":
        return HELP
    parts, done = [], state["completed"]
    if "spending" in done:
        parts.append(_spending_section(state))
    if "alerting" in done:
        al = state["alerts"]
        parts.append("Alerts\n" + ("\n".join(f"  [{x['severity'].upper()}] {x['message']}" for x in al)
                                   if al else "  No budget risks or unusual spending. You're on track."))
    if "recommendation" in done:
        recs = state["recommendations"]
        body = []
        for r in recs:
            body.append(f"  - {r['text']}" + (f"\n    How: {r['tip']}" if r["tip"] else ""))
        total = sum(r["monthly_saving"] for r in recs)
        if total:
            body.append(f"  Together these could free up about {tools.inr(round(total, -1))} a month.")
        goal = state.get("savings_goal")
        if goal and total:
            body.append(f"  Against your {tools.inr(goal)} goal, that covers {min(total / goal * 100, 999):.0f}%.")
        parts.append("Recommendations\n" + ("\n".join(body) if body else "  Nothing to cut. Spending looks healthy."))
    return "\n\n".join(parts)


def make_responder(llm):
    def responder_node(state: AdvisorState) -> dict:
        trace = list(state["trace"])
        draft = _template(state)
        answer = draft
        if llm is not None and state["intent"] != "smalltalk":
            try:
                out = llm.invoke(_llm_prompt(state, draft)).content
                answer = out if isinstance(out, str) else "".join(b.get("text", "") for b in out)
                trace.append("[responder] answer written by LLM from facts bundle")
            except Exception as exc:
                trace.append(f"[responder] LLM failed ({type(exc).__name__}); using template")
        else:
            trace.append("[responder] answer built from template")

        memory = dict(state.get("memory") or {})
        a = state.get("analysis") or {}
        top_mover = next((r["category"] for r in a.get("comparison", [])
                          if r["category"] in tools.DISCRETIONARY and (r["change_pct"] or 0) >= 15), None)
        memory.update({"last_intent": memory.get("last_intent") if state["intent"] == "smalltalk" else state["intent"], "last_month": state["month"],
                       "focus_category": state.get("focus_category") or top_mover or memory.get("focus_category"),
                       "savings_goal": state.get("savings_goal") or memory.get("savings_goal")})
        history = list(state.get("history") or []) + [
            {"role": "user", "content": state["user_query"]}, {"role": "assistant", "content": answer}]
        return {"final_response": answer, "memory": memory, "history": history, "trace": trace}
    return responder_node


def _llm_prompt(state: AdvisorState, draft: str) -> str:
    facts = {"question": state["user_query"], "intent": state["intent"], "analysis": state.get("analysis"),
             "alerts": state.get("alerts"), "recommendations": state.get("recommendations")}
    return ("You are a warm, concise retail-bank finance advisor. Answer the customer's question using ONLY "
            "the facts below; never invent numbers. Use ₹ and plain language, short sections, no markdown "
            "tables. Lead with the single most important point.\n\n"
            f"FACTS:\n{json.dumps(facts, default=str)[:12000]}\n\nDRAFT (same facts, rough):\n{draft}")
