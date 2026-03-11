"""Minimal settings for the standalone core module."""

from __future__ import annotations

import json
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
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "meta").strip().lower() or "meta"
WHATSAPP_META_VERIFY_TOKEN = os.getenv("WHATSAPP_META_VERIFY_TOKEN", "")
WHATSAPP_META_APP_SECRET = os.getenv("WHATSAPP_META_APP_SECRET", "")
WHATSAPP_META_ACCESS_TOKEN = os.getenv("WHATSAPP_META_ACCESS_TOKEN", "")
WHATSAPP_META_API_VERSION = os.getenv("WHATSAPP_META_API_VERSION", "v21.0")
WHATSAPP_META_PHONE_NUMBER_ID = os.getenv("WHATSAPP_META_PHONE_NUMBER_ID", "")
WHATSAPP_META_PROMPT_NAME = os.getenv("WHATSAPP_META_PROMPT_NAME", DEFAULT_PROMPT_NAME)
WHATSAPP_META_MODEL_NAME = os.getenv("WHATSAPP_META_MODEL_NAME", "")
WHATSAPP_META_TEMPERATURE = _get_optional_float("WHATSAPP_META_TEMPERATURE")
WHATSAPP_CALLS_VERIFY_TOKEN = os.getenv(
    "WHATSAPP_CALLS_VERIFY_TOKEN", WHATSAPP_META_VERIFY_TOKEN
)
WHATSAPP_CALLS_APP_SECRET = os.getenv("WHATSAPP_CALLS_APP_SECRET", WHATSAPP_META_APP_SECRET)
WHATSAPP_CALLS_PROMPT_NAME = os.getenv("WHATSAPP_CALLS_PROMPT_NAME", "voice_agent")
WHATSAPP_CALLS_MODEL_NAME = os.getenv("WHATSAPP_CALLS_MODEL_NAME", "")
WHATSAPP_CALLS_TEMPERATURE = _get_optional_float("WHATSAPP_CALLS_TEMPERATURE")
WHATSAPP_CALLS_INCLUDE_TTS_PAYLOAD = _get_bool("WHATSAPP_CALLS_INCLUDE_TTS_PAYLOAD", False)

# Twilio Voice
VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "twilio").strip().lower() or "twilio"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_VOICE_AUTH_TOKEN = os.getenv("TWILIO_VOICE_AUTH_TOKEN", "")
# Public base URL used to build the Gather action callback (e.g. https://xyz.ngrok.io).
# If empty, the URL is derived from the incoming request (fine behind most proxies).
TWILIO_VOICE_BASE_URL = os.getenv("TWILIO_VOICE_BASE_URL", "")
TWILIO_VOICE_PROMPT_NAME = os.getenv("TWILIO_VOICE_PROMPT_NAME", "voice_agent")
TWILIO_VOICE_MODEL_NAME = os.getenv("TWILIO_VOICE_MODEL_NAME", "")
TWILIO_VOICE_TEMPERATURE = _get_optional_float("TWILIO_VOICE_TEMPERATURE")
# Optional: E.164 number to transfer calls to a human (e.g. +521234567890)
TWILIO_VOICE_HANDOFF_NUMBER = os.getenv("TWILIO_VOICE_HANDOFF_NUMBER", "")
TWILIO_VOICE_GREETING = os.getenv(
    "TWILIO_VOICE_GREETING",
    "Hola, gracias por llamar a Kaax AI. ¿En qué puedo ayudarte hoy?",
)

# Deepgram
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_KEY", "")
DEEPGRAM_STT_MODEL = os.getenv("DEEPGRAM_STT_MODEL", "nova-3")
DEEPGRAM_STT_LANGUAGE = os.getenv("DEEPGRAM_STT_LANGUAGE", "es")
DEEPGRAM_TTS_MODEL = os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-celeste-es")

# Multi-agent supervisor
MULTI_AGENT_ENABLED = _get_bool("MULTI_AGENT_ENABLED", True)
DEMO_LINK = os.getenv("DEMO_LINK", "https://calendly.com/admin-novadream/30min")
PRICING_LINK = os.getenv("PRICING_LINK", "https://kaax.ai/#precios")

# Lead capture notifications — your personal WhatsApp number (e.g. 5215512345678)
WHATSAPP_NOTIFY_TO = os.getenv("WHATSAPP_NOTIFY_TO", "")

# ── Cost-optimization flags (all off by default for safe rollout) ──────────
ENABLE_USAGE_METRICS = _get_bool("ENABLE_USAGE_METRICS", False)
ENABLE_MODEL_ROUTER = _get_bool("ENABLE_MODEL_ROUTER", False)
ENABLE_PROMPT_COMPACT = _get_bool("ENABLE_PROMPT_COMPACT", False)
ENABLE_HISTORY_COMPRESSION = _get_bool("ENABLE_HISTORY_COMPRESSION", False)

# Model router
MODEL_ROUTER_DEFAULT = os.getenv("MODEL_ROUTER_DEFAULT", "us.amazon.nova-lite-v1:0")
MODEL_ROUTER_FALLBACK = os.getenv("MODEL_ROUTER_FALLBACK", BEDROCK_MODEL)
MODEL_ROUTER_COMPLEXITY_CHARS = _get_int("MODEL_ROUTER_COMPLEXITY_CHARS", 300)

# Prompt compaction
MAX_INPUT_USER_TEXT_CHARS = _get_int("MAX_INPUT_USER_TEXT_CHARS", 2000)
MAX_INPUT_SYSTEM_CONTEXT_CHARS = _get_int("MAX_INPUT_SYSTEM_CONTEXT_CHARS", 1000)
MODEL_MAX_OUTPUT_TOKENS = _get_int("MODEL_MAX_OUTPUT_TOKENS", 320)

# History compression
HISTORY_COMPRESS_THRESHOLD_MESSAGES = _get_int("HISTORY_COMPRESS_THRESHOLD_MESSAGES", 20)
HISTORY_COMPRESS_THRESHOLD_CHARS = _get_int("HISTORY_COMPRESS_THRESHOLD_CHARS", 8000)
HISTORY_TAIL_MESSAGES = _get_int("HISTORY_TAIL_MESSAGES", 6)
HISTORY_COMPRESS_MODEL = os.getenv("HISTORY_COMPRESS_MODEL", MODEL_ROUTER_DEFAULT)

# Memory summary: inject a Nova Lite summary of history into the system prompt.
# Activates when ENABLE_PROMPT_COMPACT=true and history >= MEMORY_SUMMARY_THRESHOLD messages.
MEMORY_SUMMARY_THRESHOLD = _get_int("MEMORY_SUMMARY_THRESHOLD", 6)

# Cost table: model_id → {input_per_1m, output_per_1m} in USD
MODEL_COST_TABLE_JSON = os.getenv(
    "MODEL_COST_TABLE_JSON",
    json.dumps({
        "us.amazon.nova-lite-v1:0": {"input_per_1m": 0.06, "output_per_1m": 0.24},
        "us.anthropic.claude-haiku-4-5-20251001-v1:0": {"input_per_1m": 0.80, "output_per_1m": 4.00},
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input_per_1m": 3.00, "output_per_1m": 15.00},
        "us.anthropic.claude-sonnet-4-6": {"input_per_1m": 3.00, "output_per_1m": 15.00},
        "global.anthropic.claude-sonnet-4-6": {"input_per_1m": 3.00, "output_per_1m": 15.00},
    }),
)

# Follow-up message sent 2h after last WhatsApp message if no demo was requested.
# Use {name} for the contact name (with leading space) or leave it out.
FOLLOW_UP_MESSAGE = os.getenv(
    "FOLLOW_UP_MESSAGE",
    "Hola{name}! Solo quería saber si tienes alguna duda sobre Kaax AI. "
    "Estoy aquí para ayudarte cuando quieras.",
)

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
