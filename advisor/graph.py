r"""LangGraph wiring.

    START -> planner -> supervisor --(conditional)--> spending       --\
                           ^   |                  \-> alerting       ---+--> back to supervisor
                           |   |                   \-> recommendation --/
                           |   \--(plan exhausted)--> respond -> END
                           \____ every specialist returns here ____/

The supervisor is a hub: it re-reads state after each specialist, may re-plan, and
picks the next hop. A MemorySaver checkpointer keeps `memory` and `history` per thread.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .agents.alerting import alerting_node
from .agents.planner import make_planner, route, supervisor_node
from .agents.recommendation import recommendation_node
from .agents.responder import make_responder
from .agents.spending import spending_node
from .llm import get_llm
from .state import AdvisorState

SPECIALISTS = {"spending": spending_node, "alerting": alerting_node, "recommendation": recommendation_node}


def build_graph(llm="auto", checkpointer=None):
    llm = get_llm() if llm == "auto" else llm
    g = StateGraph(AdvisorState)
    g.add_node("planner", make_planner(llm))
    g.add_node("supervisor", supervisor_node)
    g.add_node("respond", make_responder(llm))
    for name, fn in SPECIALISTS.items():
        g.add_node(name, fn)
        g.add_edge(name, "supervisor")

    g.add_edge(START, "planner")
    g.add_edge("planner", "supervisor")
    g.add_conditional_edges("supervisor", route, {**{n: n for n in SPECIALISTS}, "respond": "respond"})
    g.add_edge("respond", END)
    return g.compile(checkpointer=checkpointer or MemorySaver())
