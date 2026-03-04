from __future__ import annotations

import asyncio

from tools.conversation_loop_tool import conversation_loop_tool


def test_conversation_loop_tool_returns_detection_payload() -> None:
    async def run() -> None:
        first = await conversation_loop_tool.ainvoke(
            {"user_text": "hola", "scope_key": "session:abc"}
        )
        second = await conversation_loop_tool.ainvoke(
            {"user_text": "hola!!", "scope_key": "session:abc"}
        )
        third = await conversation_loop_tool.ainvoke(
            {"user_text": " hola ", "scope_key": "session:abc"}
        )

        assert first["is_repetitive"] is False
        assert second["is_repetitive"] is False
        assert third["is_repetitive"] is True
        assert third["repetition_count"] == 3
        assert third["strategy_instruction"]
        assert third["scope_key"] == "session:abc"

    asyncio.run(run())
