"""Graph-based detector for repetitive low-signal user turns."""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from settings import (
    LOOP_GRAPH_ENABLED,
    LOOP_GRAPH_MAX_MESSAGE_CHARS,
    LOOP_GRAPH_MAX_TOKENS,
    LOOP_GRAPH_THRESHOLD,
    LOOP_GRAPH_WINDOW_SECONDS,
)

_PUNCTUATION_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


class LoopGraphState(TypedDict, total=False):
    scope_key: str
    user_text: str
    now: float
    normalized_text: str
    repetition_count: int
    is_low_signal: bool
    loop_label: Literal["none", "repetitive_low_signal"]
    strategy_instruction: str


@dataclass(frozen=True)
class LoopDecision:
    is_repetitive: bool
    repetition_count: int
    normalized_text: str
    strategy_instruction: str | None


class ConversationLoopGraph:
    def __init__(
        self,
        *,
        enabled: bool,
        window_seconds: int,
        threshold: int,
        max_message_chars: int,
        max_tokens: int,
        max_events_per_scope: int = 64,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        self._enabled = enabled
        self._window_seconds = max(window_seconds, 1)
        self._threshold = max(threshold, 2)
        self._max_message_chars = max(max_message_chars, 1)
        self._max_tokens = max(max_tokens, 1)
        self._max_events_per_scope = max(max_events_per_scope, 8)
        self._time_source = time_source or time.monotonic
        self._history: dict[str, deque[tuple[float, str]]] = {}
        self._lock = asyncio.Lock()
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(LoopGraphState)
        graph.add_node("normalize_turn", self._normalize_turn)
        graph.add_node("update_window", self._update_window)
        graph.add_node("classify_loop", self._classify_loop)
        graph.add_node("build_strategy", self._build_strategy)

        graph.add_edge(START, "normalize_turn")
        graph.add_edge("normalize_turn", "update_window")
        graph.add_edge("update_window", "classify_loop")
        graph.add_conditional_edges(
            "classify_loop",
            self._route_after_classification,
            {
                "build_strategy": "build_strategy",
                "end": END,
            },
        )
        graph.add_edge("build_strategy", END)
        return graph.compile()

    async def _normalize_turn(self, state: LoopGraphState) -> LoopGraphState:
        user_text = state.get("user_text", "")
        lowered = user_text.strip().lower()
        lowered = _PUNCTUATION_RE.sub(" ", lowered)
        normalized_text = _WHITESPACE_RE.sub(" ", lowered).strip()
        return {
            "normalized_text": normalized_text,
            "now": self._time_source(),
        }

    async def _update_window(self, state: LoopGraphState) -> LoopGraphState:
        scope_key = state.get("scope_key", "unknown")
        normalized_text = state.get("normalized_text", "")
        now = state.get("now", self._time_source())
        if not normalized_text:
            return {"repetition_count": 0}

        async with self._lock:
            history = self._history.setdefault(scope_key, deque())
            cutoff = now - self._window_seconds
            while history and history[0][0] < cutoff:
                history.popleft()

            history.append((now, normalized_text))
            while len(history) > self._max_events_per_scope:
                history.popleft()

            repetition_count = sum(1 for _, text in history if text == normalized_text)

        return {"repetition_count": repetition_count}

    async def _classify_loop(self, state: LoopGraphState) -> LoopGraphState:
        normalized_text = state.get("normalized_text", "")
        repetition_count = state.get("repetition_count", 0)

        is_low_signal = (
            bool(normalized_text)
            and len(normalized_text) <= self._max_message_chars
            and len(normalized_text.split()) <= self._max_tokens
        )
        is_repetitive = (
            self._enabled and is_low_signal and repetition_count >= self._threshold
        )
        return {
            "is_low_signal": is_low_signal,
            "loop_label": "repetitive_low_signal" if is_repetitive else "none",
        }

    def _route_after_classification(
        self, state: LoopGraphState
    ) -> Literal["build_strategy", "end"]:
        if state.get("loop_label") == "repetitive_low_signal":
            return "build_strategy"
        return "end"

    async def _build_strategy(self, state: LoopGraphState) -> LoopGraphState:
        normalized_text = state.get("normalized_text", "")
        repetition_count = state.get("repetition_count", 0)
        strategy_instruction = (
            "Contexto conversacional: el usuario repitio el mismo mensaje "
            f"{repetition_count} veces en una ventana corta "
            f"(texto normalizado: '{normalized_text}'). "
            "Responde de forma natural y personalizada, "
            "evita repetir un saludo generico, reconoce brevemente el patron "
            "y haz una pregunta concreta para avanzar la conversacion."
        )
        return {"strategy_instruction": strategy_instruction}

    async def analyze(self, *, scope_key: str, user_text: str) -> LoopDecision:
        result = await self._graph.ainvoke(
            {
                "scope_key": scope_key,
                "user_text": user_text,
            }
        )

        loop_label = result.get("loop_label", "none")
        is_repetitive = loop_label == "repetitive_low_signal"
        repetition_count = int(result.get("repetition_count", 0) or 0)
        normalized_text = str(result.get("normalized_text", ""))
        strategy_instruction = result.get("strategy_instruction")
        if strategy_instruction is not None:
            strategy_instruction = str(strategy_instruction)

        return LoopDecision(
            is_repetitive=is_repetitive,
            repetition_count=repetition_count,
            normalized_text=normalized_text,
            strategy_instruction=strategy_instruction,
        )


conversation_loop_graph = ConversationLoopGraph(
    enabled=LOOP_GRAPH_ENABLED,
    window_seconds=LOOP_GRAPH_WINDOW_SECONDS,
    threshold=LOOP_GRAPH_THRESHOLD,
    max_message_chars=LOOP_GRAPH_MAX_MESSAGE_CHARS,
    max_tokens=LOOP_GRAPH_MAX_TOKENS,
)
