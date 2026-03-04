from __future__ import annotations

import asyncio

from infra.chainlit.adapter import ChainlitAdapter


def test_chainlit_adapter_maps_tool_choice() -> None:
    async def run() -> None:
        adapter = ChainlitAdapter()
        request = await adapter.normalize_inbound(
            {
                "message": "hola",
                "user": "chainlit:test-user",
                "thread_id": "chainlit:test-thread",
                "stream": True,
                "tool_choice": "required",
            }
        )

        assert request.toolChoice == "required"
        assert request.streamResponse is True
        assert request.sessionId == "chainlit:test-thread"

    asyncio.run(run())
