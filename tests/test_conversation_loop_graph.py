from __future__ import annotations

import asyncio

from tools.conversation_loop_graph import ConversationLoopGraph


def test_loop_graph_flags_repeated_low_signal_message() -> None:
    async def run() -> None:
        graph = ConversationLoopGraph(
            enabled=True,
            window_seconds=90,
            threshold=3,
            max_message_chars=24,
            max_tokens=3,
        )

        first = await graph.analyze(scope_key="wa-meta:1:2", user_text="hola")
        second = await graph.analyze(scope_key="wa-meta:1:2", user_text="Hola!!")
        third = await graph.analyze(scope_key="wa-meta:1:2", user_text=" hola ")

        assert not first.is_repetitive
        assert not second.is_repetitive
        assert third.is_repetitive
        assert third.repetition_count == 3
        assert third.strategy_instruction is not None
        assert "3 veces" in third.strategy_instruction

    asyncio.run(run())


def test_loop_graph_does_not_flag_repeated_high_signal_message() -> None:
    async def run() -> None:
        graph = ConversationLoopGraph(
            enabled=True,
            window_seconds=90,
            threshold=2,
            max_message_chars=24,
            max_tokens=3,
        )

        msg = "necesito una cotizacion detallada para una camioneta 2024"
        first = await graph.analyze(scope_key="wa-meta:1:2", user_text=msg)
        second = await graph.analyze(scope_key="wa-meta:1:2", user_text=msg)

        assert not first.is_repetitive
        assert not second.is_repetitive
        assert second.strategy_instruction is None

    asyncio.run(run())


def test_loop_graph_window_expiration_resets_repetition() -> None:
    clock = {"now": 0.0}

    def fake_time() -> float:
        return clock["now"]

    async def run() -> None:
        graph = ConversationLoopGraph(
            enabled=True,
            window_seconds=10,
            threshold=2,
            max_message_chars=24,
            max_tokens=3,
            time_source=fake_time,
        )

        first = await graph.analyze(scope_key="wa-meta:1:2", user_text="hola")
        assert not first.is_repetitive

        clock["now"] = 11.0
        second = await graph.analyze(scope_key="wa-meta:1:2", user_text="hola")
        assert not second.is_repetitive
        assert second.repetition_count == 1

    asyncio.run(run())
