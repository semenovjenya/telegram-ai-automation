"""Measure the existing prompt-history limit on deterministic synthetic messages.

UTF-8 JSON bytes, not billed tokens/cost/latency. Trimming is deliberately lossy.
"""

from __future__ import annotations

import json
from pathlib import Path

from examples.demo_environment import configure_demo

configure_demo()

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402

from ai_brain.nodes.agent_runtime import build_messages  # noqa: E402


def message_bytes(messages) -> int:
    value = [{"role": m.type, "content": m.content} for m in messages]
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def measure() -> dict:
    results = []
    for count in (10, 50):
        history = [
            (HumanMessage if index % 2 == 0 else AIMessage)(
                content=f"Synthetic turn {index:03}: " + "channel analytics demo " * 10
            )
            for index in range(count)
        ]
        current = "Explain the latest demo metrics"
        system = "Use only synthetic channel analytics."
        baseline = [
            SystemMessage(content=system),
            *history,
            HumanMessage(content=current),
        ]
        bounded = build_messages(
            system,
            {
                "history": [*history, HumanMessage(content=current)],
                "message_text": current,
            },
        )
        before, after = message_bytes(baseline), message_bytes(bounded)
        assert sum(m.content == current for m in bounded) == 1
        assert bounded[-1].content == current
        assert len(bounded) <= 32
        results.append(
            {
                "loaded_history_messages": count,
                "baseline_messages": len(baseline),
                "bounded_messages": len(bounded),
                "baseline_bytes": before,
                "bounded_bytes": after,
                "reduction_percent": round(100 * (before - after) / before, 2),
                "older_messages_omitted": max(0, count - 30),
                "current_message_copies": 1,
            }
        )
    return {
        "measurement": "UTF-8 bytes of canonical role/content JSON",
        "baseline": "All messages of the loaded window, current user message once",
        "scope": "Synthetic inputs; older history is omitted, not losslessly compressed; no quality or billing claim",
        "cases": results,
    }


if __name__ == "__main__":
    rendered = json.dumps(measure(), indent=2) + "\n"
    print(rendered, end="")
    Path("benchmarks/results.json").write_text(rendered)
