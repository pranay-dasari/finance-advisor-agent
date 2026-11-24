"""Optional LLM. With ANTHROPIC_API_KEY set, the Planner reasons with Claude and the
Responder writes the final answer with it. Without a key (or with ADVISOR_NO_LLM=1)
every node falls back to deterministic logic, so the prototype always runs offline.
"""
from __future__ import annotations

import os


def get_llm():
    if os.getenv("ADVISOR_NO_LLM") == "1" or not os.getenv("ANTHROPIC_API_KEY"):
        return None
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=os.getenv("ADVISOR_MODEL", "claude-sonnet-5-5"), max_tokens=1024)
