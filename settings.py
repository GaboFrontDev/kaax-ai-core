"""Minimal settings for the standalone core module."""

from __future__ import annotations

import os
from os.path import dirname, join

from dotenv import load_dotenv


load_dotenv(join(dirname(__file__), ".env"))


def _get_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_optional_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# API
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_COLORIZED = _get_bool("LOG_COLORIZED", True)
API_TOKENS = [
    token.strip()
    for token in os.getenv("API_TOKENS", "dev-token").split(",")
    if token.strip()
]
LOOP_GRAPH_ENABLED = _get_bool("LOOP_GRAPH_ENABLED", True)
LOOP_GRAPH_WINDOW_SECONDS = _get_int("LOOP_GRAPH_WINDOW_SECONDS", 90)
LOOP_GRAPH_THRESHOLD = _get_int("LOOP_GRAPH_THRESHOLD", 1)
LOOP_GRAPH_MAX_MESSAGE_CHARS = _get_int("LOOP_GRAPH_MAX_MESSAGE_CHARS", 24)
LOOP_GRAPH_MAX_TOKENS = _get_int("LOOP_GRAPH_MAX_TOKENS", 1)

# Bedrock / model
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
BEDROCK_MODEL = (
    os.getenv("BEDROCK_MODEL")
    or os.getenv("MODEL_NAME")
    or "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
DEFAULT_TEMPERATURE = _get_float("DEFAULT_TEMPERATURE", 0.5)

# Agent prompt
DEFAULT_PROMPT_NAME = os.getenv("DEFAULT_PROMPT_NAME", "agent")

# Checkpoints DB
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DB_DSN") or ""
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "core")

# WhatsApp Meta
WHATSAPP_META_VERIFY_TOKEN = os.getenv("WHATSAPP_META_VERIFY_TOKEN", "")
WHATSAPP_META_APP_SECRET = os.getenv("WHATSAPP_META_APP_SECRET", "")
WHATSAPP_META_ACCESS_TOKEN = os.getenv("WHATSAPP_META_ACCESS_TOKEN", "")
WHATSAPP_META_API_VERSION = os.getenv("WHATSAPP_META_API_VERSION", "v21.0")
WHATSAPP_META_PHONE_NUMBER_ID = os.getenv("WHATSAPP_META_PHONE_NUMBER_ID", "")
WHATSAPP_META_PROMPT_NAME = os.getenv("WHATSAPP_META_PROMPT_NAME", DEFAULT_PROMPT_NAME)
WHATSAPP_META_MODEL_NAME = os.getenv("WHATSAPP_META_MODEL_NAME", "")
WHATSAPP_META_TEMPERATURE = _get_optional_float("WHATSAPP_META_TEMPERATURE")

# Multi-agent supervisor
MULTI_AGENT_ENABLED = _get_bool("MULTI_AGENT_ENABLED", True)
DEMO_LINK = os.getenv("DEMO_LINK", "https://calendly.com/admin-novadream/30min")
PRICING_LINK = os.getenv("PRICING_LINK", "https://kaax.ai/#precios")

# Optional lightweight prompt-sanitizer rules
BLOCK_PATTERNS = [
    r"system\\s+prompt",
    r"system\\s+instructions",
    r"(forget|ignore|discard)\\s+(everything|all)\\s+(before|above|prior|previous)",
    r"<[^>]+>",
]

BLOCK_WORDS = [
    "instructions",
    "ignore",
    "prompt",
    "override",
    "jailbreak",
]
