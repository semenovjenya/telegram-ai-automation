import asyncio

import pytest

from ai_brain.clients.channel_search_client import (
    MAX_FORMATTED_RESULTS_CHARS,
    ChannelSearchClient,
)


def test_channel_results_are_formatted_for_rag() -> None:
    formatted = ChannelSearchClient.format_results(
        [{"text": "Audience: founders", "source": "channel:example"}]
    )
    assert formatted is not None
    assert "Audience: founders" in formatted
    assert "channel:example" in formatted


def test_channel_search_rejects_unbounded_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ChannelSearchClient()
    monkeypatch.setattr(type(client), "base_url", property(lambda _: "http://test"))
    with pytest.raises(ValueError, match="top_k"):
        asyncio.run(client.search("query", "example", top_k=21))


def test_channel_results_are_bounded_before_prompt_insertion() -> None:
    formatted = ChannelSearchClient.format_results(
        [
            {"text": f"result-{index}-" + "x" * 20_000, "source": "s" * 2_000}
            for index in range(30)
        ]
    )

    assert formatted is not None
    assert len(formatted) <= MAX_FORMATTED_RESULTS_CHARS
    assert "result-0" in formatted
    assert "result-5" not in formatted
