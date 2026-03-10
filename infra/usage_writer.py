"""Async writer for llm_usage_events. Fire-and-forget; errors are logged, never raised."""

from __future__ import annotations

import json
import logging
from decimal import Decimal

import psycopg

from settings import MODEL_COST_TABLE_JSON
from sql_utilities import get_database_url

logger = logging.getLogger(__name__)

_cost_table: dict[str, dict] = {}
try:
    _cost_table = json.loads(MODEL_COST_TABLE_JSON)
except Exception:
    pass


def _estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    rates = _cost_table.get(model_id)
    if not rates:
        return None
    try:
        cost = Decimal(str(rates["input_per_1m"])) * input_tokens / 1_000_000
        cost += Decimal(str(rates["output_per_1m"])) * output_tokens / 1_000_000
        return cost
    except Exception:
        return None


async def write_usage_event(
    *,
    channel: str = "api",
    requestor: str | None = None,
    thread_id: str | None = None,
    run_id: str | None = None,
    route_tier: str | None = None,
    model_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    latency_ms: int | None = None,
    success: bool = True,
    error: str | None = None,
) -> None:
    total = input_tokens + output_tokens
    estimated_cost = _estimate_cost(model_id or "", input_tokens, output_tokens) if model_id else None

    try:
        url = get_database_url()
        async with await psycopg.AsyncConnection.connect(url) as conn:
            await conn.execute(
                """
                INSERT INTO llm_usage_events
                    (channel, requestor, thread_id, run_id, route_tier, model_id,
                     input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                     total_tokens, estimated_cost_usd, latency_ms, success, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    channel, requestor, thread_id, run_id, route_tier, model_id,
                    input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                    total, estimated_cost, latency_ms, success, error,
                ),
            )
    except Exception:
        logger.exception("usage_writer: failed to write usage event")
