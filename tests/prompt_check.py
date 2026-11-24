"""Runs the challenge brief's examples + varied phrasings; prints plan, agents run, and key output."""
import uuid
from advisor.graph import build_graph

app = build_graph(llm=None)
def run(q, t):
    o = app.invoke({"user_query": q}, config={"configurable": {"thread_id": t}})
    plan = [l for l in o["trace"] if "[planner] (" in l][0].split("] ", 1)[1]
    print(f"\n### {q}\n  {plan}\n  ran: {o['completed']}")
    return o

t = str(uuid.uuid4())
o = run("How can I improve my monthly savings?", t)
print("\n".join("  " + l for l in o["final_response"].splitlines()[:30]))
for q in ["How much did I spend on travel?", "Am I overspending anywhere?", "Where is my money going?",
          "Can you cut my entertainment costs?", "I want to save 8000 a month, how?", "and what about shopping?",
          "Is anything unusual in my transactions?", "How was September?", "thanks", "Am I rich?",
          "Show food spending for last month"]:
    run(q, t)
