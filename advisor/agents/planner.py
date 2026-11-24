"""PLANNER + SUPERVISOR: the in-depth agent (orchestration brain of the system).

Reasoning flow, per turn:
  1. UNDERSTAND   parse intent, month, category focus and savings goal from the query,
                  resolving follow-ups ("what about food?", "how much would I save?")
                  from conversation memory.
  2. PLAN         choose which specialists to run and in what order. Uses Claude with
                  structured output when a key is configured; otherwise rule-based.
  3. VALIDATE     the LLM's plan is never trusted blindly: unknown agents are dropped,
                  dependencies are enforced (recommendation and alerting need the
                  spending analysis first) and ordering is made canonical.
  4. SUPERVISE    after every specialist finishes, decide the next hop and re-plan
                  when what was found changes what is needed (e.g. an unusual
                  transaction appears, so the Alerting agent is added even though
                  the user only asked for a spending summary).
  5. HAND OFF     when the plan is exhausted, route to the Responder, which merges
                  every specialist's output into one answer.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .. import data, tools
from ..state import AdvisorState

AgentName = Literal["spending", "alerting", "recommendation"]
CANONICAL_ORDER = ["spending", "alerting", "recommendation"]
NEEDS_SPENDING = {"alerting", "recommendation"}
MAX_STEPS = 8  # loop guard for the supervisor

CATEGORY_ALIASES = {
    "Food": ["food", "dining", "eating out", "delivery", "swiggy", "zomato", "restaurant"],
    "Groceries": ["grocery", "groceries", "bigbasket", "blinkit"],
    "Shopping": ["shopping", "shop", "amazon", "myntra", "clothes", "electronics"],
    "Travel": ["travel", "cab", "uber", "ola", "commute", "transport"],
    "Entertainment": ["entertainment", "movie", "netflix", "spotify", "games", "streaming"],
    "Bills": ["bill", "bills", "rent", "electricity", "utilities"],
}
MONTH_NAMES = {n: i for i, n in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}

INTENT_AGENTS = {
    "smalltalk": [],
    "spending_summary": ["spending"],
    "improve_savings": ["spending", "recommendation"],
    "alerts": ["spending", "alerting"],
    "category_deep_dive": ["spending", "recommendation"],
    "financial_health": ["spending", "alerting", "recommendation"],
}


class PlanSpec(BaseModel):
    """Structured output the planner LLM must produce."""
    intent: Literal["smalltalk", "spending_summary", "improve_savings", "alerts",
                    "category_deep_dive", "financial_health"]
    agents: list[AgentName] = Field(description="Specialist agents to run")
    category: Optional[str] = Field(None, description="Food, Groceries, Shopping, Travel, Entertainment, Bills")
    month: Optional[str] = Field(None, description="YYYY-MM if the user named a month")
    savings_goal: Optional[float] = Field(None, description="Monthly rupee savings target if stated")
    rationale: str = Field(description="One sentence on why this plan")


# ------------------------------------------------------------------ understand
def _detect_category(q: str) -> str | None:
    for cat, words in CATEGORY_ALIASES.items():
        if any(re.search(rf"\b{re.escape(w)}", q) for w in words):
            return cat
    return None


def _detect_month(q: str) -> str | None:
    cur = f"{data.AS_OF.year}-{data.AS_OF.month:02d}"
    if "last month" in q or "previous month" in q:
        return tools.previous_month(cur)
    if "this month" in q:
        return cur
    for name, num in MONTH_NAMES.items():
        if re.search(rf"\b{name}\b", q):
            return f"{data.AS_OF.year}-{num:02d}"
    return None


def _detect_goal(q: str) -> float | None:
    m = re.search(r"save\s*(?:about|around|upto|up to)?\s*(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(k|l|lakh)?", q)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    return val * {"k": 1_000, "l": 100_000, "lakh": 100_000}.get(m.group(2) or "", 1)


def _rule_based(q: str, memory: dict) -> dict:
    """Deterministic fallback with the same output shape as the LLM path.

    Order matters: more specific intents are tested before generic ones.
    """
    has = lambda *ws: any(re.search(rf"\b{w}", q) for w in ws)  # noqa: E731
    cat = _detect_category(q)
    followup = has("what about", "how about", "and", "that", "those")  # explicit follow-up cues only

    if has("hi", "hello", "hey", "thanks", "thank", "help") and not (cat or has("spend", "save", "alert")):
        intent = "smalltalk"
    elif has("alert", "warn", "limit", "nearing", "overspend", "unusual", "spike", "risk", "anomal", "suspicious"):
        intent = "alerts"
    elif has("save", "saving", "improve", "reduce", "cut", "optimi[sz]e", "lower", "budget", "how much would"):
        cat = cat or (memory.get("focus_category") if has("how much would", "that") else None)
        intent = "category_deep_dive" if cat else "improve_savings"
    elif cat and has("why", "explain", "high", "too much"):
        intent = "category_deep_dive"          # diagnose + advise
    elif has("overall", "health", "how am i", "report", "everything", "review", "doing"):
        intent = "financial_health"
    elif has("spend", "spent", "summary", "breakdown", "how much", "categor", "trend", "expense",
             "transaction", "show", "money going", "money go", "how was", "what did i"):
        intent = "spending_summary"            # factual question: numbers only, no advice
    elif cat:
        intent = "category_deep_dive"          # bare category, e.g. "what about food?"
    elif followup and memory.get("last_intent"):
        intent = memory["last_intent"]
    else:
        intent = "financial_health"

    return {"intent": intent, "agents": list(INTENT_AGENTS[intent]), "category": cat,
            "month": _detect_month(q), "savings_goal": _detect_goal(q), "followup": followup,
            "rationale": f"rule-based: matched intent '{intent}'"}


def _llm_plan(llm, query: str, memory: dict, history: list[dict]) -> dict:
    prompt = (
        "You are the Planner of a retail-bank personal finance advisor made of specialist agents:\n"
        "- spending: reads and categorises transactions, month totals, trends, unusual transactions\n"
        "- alerting: budget limits, projected overspend, spikes\n"
        "- recommendation: savings and budget-optimisation advice (needs spending)\n"
        f"Today is {data.AS_OF.isoformat()}. Categories: {', '.join(data.BUDGETS)}.\n"
        f"Conversation memory: {memory}\nRecent turns: {history[-4:]}\n"
        "Resolve follow-ups from memory. Pick the smallest set of agents that fully answers the user.\n"
        f"User: {query}"
    )
    return llm.with_structured_output(PlanSpec).invoke(prompt).model_dump()


# ---------------------------------------------------------------------- validate
def _normalize(spec: dict) -> dict:
    agents = {a for a in spec.get("agents", []) if a in CANONICAL_ORDER}
    if agents & NEEDS_SPENDING:
        agents.add("spending")
    spec["agents"] = [a for a in CANONICAL_ORDER if a in agents]
    cat = spec.get("category")
    spec["category"] = next((c for c in data.BUDGETS if cat and c.lower() == cat.lower()), None)
    month = spec.get("month")
    spec["month"] = month if month in data.MONTHS else None
    return spec


# ------------------------------------------------------------------------- nodes
def make_planner(llm):
    def planner_node(state: AdvisorState) -> dict:
        query = state["user_query"].strip()
        memory = dict(state.get("memory") or {})
        history = list(state.get("history") or [])
        trace = [f"[planner] query: {query!r}"]

        spec, source = None, "rules"
        if llm is not None:
            try:
                spec, source = _llm_plan(llm, query, memory, history), "llm"
            except Exception as exc:  # network/key/schema errors must never kill the turn
                trace.append(f"[planner] LLM planning failed ({type(exc).__name__}); using rules")
        if spec is None:
            spec = _rule_based(query.lower(), memory)
        spec = _normalize(spec)

        # a remembered month only carries over into follow-ups, never into a fresh question
        month = spec["month"] or _detect_month(query.lower()) \
            or (memory.get("last_month") if spec.get("followup") else None) \
            or f"{data.AS_OF.year}-{data.AS_OF.month:02d}"
        goal = spec.get("savings_goal") or _detect_goal(query.lower()) or memory.get("savings_goal")
        trace.append(f"[planner] ({source}) intent={spec['intent']} month={month} "
                     f"focus={spec['category']} goal={goal} plan={spec['agents']}")
        trace.append(f"[planner] why: {spec['rationale']}")

        # Everything per-turn is reset here so stale checkpointed values never leak across turns.
        return {"intent": spec["intent"], "month": month, "focus_category": spec["category"],
                "savings_goal": goal, "plan": spec["agents"], "completed": [], "steps": 0,
                "analysis": {}, "recommendations": [], "alerts": [], "final_response": "",
                "trace": trace}
    return planner_node


def supervisor_node(state: AdvisorState) -> dict:
    """Runs between every hop: re-plan if findings warrant it, then pick the next agent."""
    plan, done = list(state["plan"]), list(state["completed"])
    trace = list(state["trace"])
    steps = state.get("steps", 0) + 1

    if "spending" in done and "alerting" not in plan:
        a, focus = state.get("analysis", {}), state.get("focus_category")
        mine = lambda cat: not focus or cat == focus  # noqa: E731  only findings in scope trigger a re-plan
        hot = [b for b in a.get("budget_status", [])
               if mine(b["category"]) and (b["pct_used"] >= 80 or b["projected_pct"] >= 100)]
        unusual = [t for t in a.get("anomalies", []) if mine(t["category"])]
        if unusual or hot:
            plan.insert(plan.index("recommendation") if "recommendation" in plan else len(plan), "alerting")
            why = f"{len(unusual)} unusual txn(s), {len(hot)} budget(s) running hot"
            trace.append(f"[supervisor] re-plan: added 'alerting' ({why})")

    pending = [a for a in plan if a not in done]
    if steps > MAX_STEPS:
        trace.append("[supervisor] step limit hit; going to respond")
        pending = []
    nxt = pending[0] if pending else "respond"
    trace.append(f"[supervisor] done={done} -> next={nxt}")
    return {"plan": plan, "next_agent": nxt, "steps": steps, "trace": trace}


def route(state: AdvisorState) -> str:
    return state["next_agent"]
