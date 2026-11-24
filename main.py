"""CLI for the Personal Finance Advisor.

  python main.py                 interactive chat (remembers context within the session)
  python main.py --demo          scripted multi-turn demo
  python main.py -v              also print each agent's reasoning trace
  python main.py --graph         print the LangGraph structure as Mermaid
"""
import argparse
import uuid

from advisor.graph import build_graph
from advisor.llm import get_llm

DEMO = [
    "How can I improve my monthly savings?",
    "What about food?",
    "Any budget alerts for me?",
    "Show my spending breakdown for last month",
]


def ask(app, query: str, thread: str, verbose: bool) -> None:
    out = app.invoke({"user_query": query}, config={"configurable": {"thread_id": thread}})
    print(f"\nYou: {query}")
    if verbose:
        print("\n  --- reasoning trace ---")
        print("\n".join("  " + line for line in out["trace"]))
        print("  -----------------------")
    print(f"\nAdvisor:\n{out['final_response']}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--graph", action="store_true")
    args = ap.parse_args()

    llm = get_llm()
    app = build_graph(llm)
    if args.graph:
        print(app.get_graph().draw_mermaid())
        return
    print(f"[mode: {'Claude-planned' if llm else 'offline rule-based (set ANTHROPIC_API_KEY for LLM)'}]")
    thread = str(uuid.uuid4())
    if args.demo:
        for q in DEMO:
            ask(app, q, thread, args.verbose)
        return
    print("Ask about your finances (empty line to quit).")
    while (q := input("\nYou: ").strip()):
        ask(app, q, thread, args.verbose)


if __name__ == "__main__":
    main()
