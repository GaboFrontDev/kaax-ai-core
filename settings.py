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


# API
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_COLORIZED = _get_bool("LOG_COLORIZED", True)
API_TOKENS = [
    token.strip()
    for token in os.getenv("API_TOKENS", "dev-token").split(",")
    if token.strip()
]

# Bedrock / model
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
DEFAULT_TEMPERATURE = _get_float("DEFAULT_TEMPERATURE", 0.5)

# Agent prompt
DEFAULT_PROMPT_NAME = os.getenv("DEFAULT_PROMPT_NAME", "agent")

# Checkpoints DB
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "core")

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
