# Prototype Demonstration

## Run it yourself

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py          # web UI at http://localhost:8501
.venv/bin/python main.py --demo -v      # scripted CLI demo with the reasoning trace
```

No API key is needed. The full output of the scripted demo is saved in
[demo_transcript.txt](demo_transcript.txt).

## Suggested demo script (about 3 minutes)

| Say / type | What it shows |
|---|---|
| "How can I improve my monthly savings?" | The brief's own example. Planner plans spending → recommendation; the Supervisor **adds alerting** mid-run; ranked ₹ savings come back. Open *Agent reasoning trace*. |
| "What about food?" | **Memory**: follow-up resolved from context; answer narrows to Food. Watch the sidebar's Agent memory panel. |
| "How much did I spend on travel?" | **Autonomous planning**: a factual question runs only the Spending agent, no advice. |
| "Any budget alerts for me?" | Alerting agent: critical / warning / info with budget percentages. |
| "I want to save 8000 a month, how?" then "and what about shopping?" | Goal parsed, remembered, and applied to the next turn. |
| "How was September?" | Month parsing; a past month is complete (no "so far"). |

## What the mock data contains (so you know what to expect)

Data is "as of" 24 Nov 2026. November food spend is up 21% on the same days of October, entertainment is at
98% of its budget, shopping is over budget because of one ₹6,999 Croma purchase that is flagged as unusual,
and the savings rate is 39%.

## Screens

- **Chat (left):** conversation, the newest question scrolled into view, a reasoning-trace expander per answer.
- **Budget dashboard (right):** spend, income, savings rate, per-category budget bars, current-vs-previous chart, alert boxes.
- **Sidebar:** sample questions, live agent memory, new conversation.
