"""Model factory for the minimal core agent (Bedrock-only)."""

from __future__ import annotations

from typing import Optional

from langchain_aws import ChatBedrockConverse

from settings import AWS_REGION, BEDROCK_MODEL


def get_model(
    model_name: str = BEDROCK_MODEL,
    streaming: bool = True,
    max_retries: int = 1,
    temperature: float = 0.5,
    max_tokens: Optional[int] = None,
):
    """Return a Bedrock chat model instance."""
    _ = max_retries

    kwargs = dict(
        model_id=model_name,
        region_name=AWS_REGION,
        temperature=temperature,
        disable_streaming=not streaming,
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    return ChatBedrockConverse(**kwargs)
