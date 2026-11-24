"""Shared graph state. One TypedDict flows through every node.

Per-turn fields are reset by the planner each turn. `memory` and `history`
survive across turns because the graph is compiled with a checkpointer and
invoked with a stable thread_id.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AdvisorState(TypedDict, total=False):
    # input
    user_query: str

    # planner output (per turn)
    intent: str
    month: str
    focus_category: str | None
    savings_goal: float | None
    plan: list[str]            # ordered specialist agents to run
    completed: list[str]       # agents that have finished this turn
    next_agent: str            # set by the supervisor, read by the router
    steps: int                 # loop guard

    # specialist outputs (per turn)
    analysis: dict[str, Any]
    recommendations: list[dict]
    alerts: list[dict]

    # output + observability
    final_response: str
    trace: list[str]

    # memory (persists across turns)
    memory: dict[str, Any]     # focus_category, savings_goal, last_intent, last_month
    history: list[dict]        # [{"role": "user"|"assistant", "content": str}]
