import uuid

import pytest

from advisor import tools
from advisor.agents.planner import _normalize, _rule_based
from advisor.graph import build_graph


@pytest.fixture
def app():
    return build_graph(llm=None)  # deterministic, no network


def run(app, q, thread=None):
    cfg = {"configurable": {"thread_id": thread or str(uuid.uuid4())}}
    return app.invoke({"user_query": q}, config=cfg)


def test_savings_query_runs_spending_then_recommendation(app):
    out = run(app, "How can I improve my monthly savings?")
    assert out["completed"][0] == "spending"
    assert "recommendation" in out["completed"]
    assert out["recommendations"] and "monthly" in out["final_response"]


def test_supervisor_replans_to_add_alerting(app):
    # user only asked for a summary, but an unusual transaction exists -> alerting is added
    out = run(app, "Show my spending breakdown")
    assert "alerting" in out["completed"]
    assert any("[supervisor] re-plan" in t for t in out["trace"])


def test_dependencies_enforced():
    spec = _normalize({"intent": "alerts", "agents": ["recommendation"], "category": None, "month": None})
    assert spec["agents"] == ["spending", "recommendation"]
    spec = _normalize({"intent": "x", "agents": ["bogus", "alerting"], "category": "food", "month": "1999-01"})
    assert spec["agents"] == ["spending", "alerting"] and spec["category"] == "Food" and spec["month"] is None


def test_followup_uses_memory(app):
    t = str(uuid.uuid4())
    run(app, "How can I improve my monthly savings?", t)
    out = run(app, "what about food?", t)
    assert out["focus_category"] == "Food"
    assert set(out["memory"]) >= {"last_intent", "focus_category"}
    assert len(out["history"]) == 4


def test_savings_goal_remembered_across_turns(app):
    t = str(uuid.uuid4())
    run(app, "I want to save 5000 a month, what should I do?", t)
    out = run(app, "and what about shopping?", t)
    assert out["savings_goal"] == 5000


def test_smalltalk_runs_no_agents(app):
    out = run(app, "hello")
    assert out["completed"] == [] and "Ask me" in out["final_response"]


def test_per_turn_state_resets(app):
    t = str(uuid.uuid4())
    run(app, "Any budget alerts?", t)
    out = run(app, "hello", t)
    assert out["alerts"] == [] and out["analysis"] == {}


def test_like_for_like_comparison():
    txns = tools.categorize_transactions(tools.get_transactions())
    upto, _ = tools.month_window("2026-11")
    assert upto == 24
    nov = tools.monthly_totals(txns, "2026-11", upto)
    oct_same = tools.monthly_totals(txns, "2026-10", upto)
    oct_full = tools.monthly_totals(txns, "2026-10")
    assert sum(oct_same.values()) < sum(oct_full.values())
    assert sum(nov.values()) > sum(oct_same.values())


def test_anomaly_found_and_bills_ignored():
    txns = tools.categorize_transactions(tools.get_transactions())
    found = tools.detect_anomalies(txns, "2026-11")
    assert [t["description"] for t in found] == ["CROMA ELECTRONICS"]


def test_inr_indian_grouping():
    assert tools.inr(1234567) == "₹12,34,567"
    assert tools.inr(12000) == "₹12,000"
    assert tools.inr(999) == "₹999"


def test_rules_parse_month_and_rule_intents():
    assert _rule_based("alerts for last month", {})["month"] == "2026-10"
    assert _rule_based("any unusual spending?", {})["intent"] == "alerts"


def test_factual_question_runs_no_advice(app):
    out = run(app, "How much did I spend on travel?")
    assert out["completed"] == ["spending"] and out["recommendations"] == []


def test_replan_only_for_findings_in_scope(app):
    # travel is fine, so asking about travel must not pull in alerting
    assert "alerting" not in run(app, "How much did I spend on travel?")["completed"]
    assert "alerting" in run(app, "Can you cut my entertainment costs?")["completed"]


def test_month_and_smalltalk_do_not_leak_between_questions(app):
    t = str(uuid.uuid4())
    assert run(app, "How was September?", t)["month"] == "2026-09"
    run(app, "thanks", t)
    out = run(app, "Am I rich?", t)
    assert out["month"] == "2026-11" and out["intent"] == "financial_health"
    assert out["memory"]["last_intent"] != "smalltalk"
