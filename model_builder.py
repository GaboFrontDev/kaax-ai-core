"""Model factory for the minimal core agent (Bedrock-only)."""

from __future__ import annotations

from langchain_aws import ChatBedrockConverse

from settings import AWS_REGION, BEDROCK_MODEL



def get_model(
    model_name: str = BEDROCK_MODEL,
    streaming: bool = True,
    max_retries: int = 1,
    temperature: float = 0.5,
):
    """Return a Bedrock chat model instance.

    The signature mirrors the existing project convention.
    """
    # Kept for compatibility with the existing project signature.
    _ = max_retries

    return ChatBedrockConverse(
        model_id=model_name,
        region_name=AWS_REGION,
        temperature=temperature,
        disable_streaming=not streaming,
    )
