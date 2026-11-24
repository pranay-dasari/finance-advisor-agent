"""Streamlit web UI for the Personal Finance Advisor.  Run: streamlit run app.py"""
import uuid

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from advisor import data, tools
from advisor.graph import build_graph
from advisor.llm import get_llm

st.set_page_config(page_title="Finance Advisor", page_icon="₹", layout="wide")

SUGGESTIONS = [
    "How can I improve my monthly savings?",
    "Any budget alerts for me?",
    "Show my spending breakdown",
    "What about food?",
    "How is my overall financial health?",
]

if "app" not in st.session_state:  # one graph + checkpointer thread per browser session
    llm = get_llm()
    st.session_state.app = build_graph(llm)
    st.session_state.thread = str(uuid.uuid4())
    st.session_state.mode = "Claude-planned" if llm else "Offline (rule-based)"
    st.session_state.chat = []      # [{"role", "content", "trace"}]
    st.session_state.last = None    # last graph output, drives the dashboard


def ask(query: str) -> None:
    out = st.session_state.app.invoke(
        {"user_query": query}, config={"configurable": {"thread_id": st.session_state.thread}})
    st.session_state.chat += [{"role": "user", "content": query},
                              {"role": "assistant", "content": out["final_response"], "trace": out["trace"]}]
    if out.get("analysis"):
        st.session_state.last = out
    st.session_state.memory = out.get("memory", {})


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("₹ Finance Advisor")
    st.caption(f"Mode: {st.session_state.mode}")
    st.caption(f"Data as of {data.AS_OF:%d %b %Y} (mock transactions)")
    st.subheader("Try asking")
    for s in SUGGESTIONS:
        if st.button(s, width="stretch"):
            st.session_state.pending = s
    st.subheader("Agent memory")
    mem_box = st.container()  # filled after the query is processed so it is never one turn stale
    if st.button("New conversation", width="stretch"):
        for k in ("app", "thread", "chat", "last", "memory", "pending"):
            st.session_state.pop(k, None)
        st.rerun()

# --------------------------------------------------------------------- main
# chat_input at page level (not inside a column) is pinned to the bottom of the window
query = st.chat_input("Ask about your spending, savings or budgets") or st.session_state.pop("pending", None)
if query:
    with st.spinner("Agents working..."):
        ask(query)
mem_box.json(st.session_state.get("memory") or {"info": "nothing remembered yet"})

chat_col, dash_col = st.columns([1, 1], gap="large")

with dash_col:
    st.subheader("Budget dashboard")
    last = st.session_state.last
    if not last:
        st.info("Ask a question and the numbers behind the answer appear here.")
    else:
        a = last["analysis"]
        c1, c2, c3 = st.columns(3)
        chg = ((a["total_spend"] - a["prev_total_spend"]) / a["prev_total_spend"] * 100) if a["prev_total_spend"] else 0
        c1.metric("Spent", tools.inr(a["total_spend"]), f"{chg:+.0f}%", delta_color="inverse")
        c2.metric("Income", tools.inr(a["income"]))
        c3.metric("Savings rate", f"{a['savings_rate']:.0f}%")
        st.caption(f"{a['month']}, days 1-{a['upto_day']}. Spent change is vs the same days last month.")

        rows = [{"Category": b["category"], "Spent": b["spent"], "Budget": b["budget"],
                 "Used %": round(b["pct_used"])} for b in a["budget_status"]]
        df = pd.DataFrame(rows)
        st.dataframe(
            df, hide_index=True, width="stretch",
            column_config={"Spent": st.column_config.NumberColumn(format="₹%d"),
                           "Budget": st.column_config.NumberColumn(format="₹%d"),
                           "Used %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%")})
        st.bar_chart(pd.DataFrame(
            {"Previous (same days)": [a["prev_totals"].get(r["Category"], 0) for r in rows],
             "Current": [a["totals"].get(r["Category"], 0) for r in rows]},
            index=[r["Category"] for r in rows]))
        for al in last.get("alerts", []):
            {"critical": st.error, "warning": st.warning, "info": st.info}[al["severity"]](al["message"])

with chat_col:
    st.subheader("Chat")
    # fixed-height scroll area: older messages move up, the newest stays in view
    box = st.container(height=640, border=False)
    with box:
        if not st.session_state.chat:
            st.caption("Ask a question below, or pick one from the sidebar.")
        for m in st.session_state.chat:
            with st.chat_message(m["role"]):
                if m["role"] == "assistant":
                    st.text(m["content"])
                else:
                    st.write(m["content"])
                if m.get("trace"):
                    with st.expander("Agent reasoning trace"):
                        st.code("\n".join(m["trace"]), language="text")
    if st.session_state.chat:
        # scroll the chat area so the newest question and the start of its answer are visible; no-op if blocked
        components.html(
            f"""<script>/* turn {len(st.session_state.chat)} */
            const go = () => {{
              const msgs = window.parent.document.querySelectorAll('[data-testid="stChatMessage"]');
              const last = msgs[Math.max(0, msgs.length - 2)];  // newest question: its answer follows below
              if (last) {{ last.style.scrollMarginTop = '70px'; last.scrollIntoView({{block: 'start'}}); }}
            }};
            go(); setTimeout(go, 150); setTimeout(go, 500);  // re-apply once layout has settled
            </script>""", height=0)
