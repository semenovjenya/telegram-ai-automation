"""Public demo and context benchmark contracts, without external services."""

import asyncio
import socket

from benchmarks.context_budget import measure
from examples.offline_demo import run_demo


def test_demo_routes_and_stores_history_without_network(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("Offline demo attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    result = asyncio.run(run_demo())
    assert [item["route"] for item in result["scenarios"]] == [
        "GENERAL",
        "SALES",
        "BARTER",
    ]
    assert all(item["stored_messages"] == 2 for item in result["scenarios"])


def test_context_budget_reports_trimming_and_keeps_short_history():
    short, long = measure()["cases"]
    assert short["baseline_bytes"] == short["bounded_bytes"]
    assert short["older_messages_omitted"] == 0
    assert long["older_messages_omitted"] == 20
    assert long["bounded_messages"] == 32
    assert long["bounded_bytes"] < long["baseline_bytes"]
    assert long["current_message_copies"] == 1
