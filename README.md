# Kaax AI Core

A generic engine for building production conversational agents with **LangGraph + FastAPI + AWS Bedrock**.

It is designed to run as a git submodule inside a **client repo** that provides the business-specific
logic (prompts, tools, funnel state). The engine knows nothing about the client. It receives a
`ClientConfig` at startup and uses it for everything.

**Highlights**

- Multi-agent supervisor that routes each turn to a specialist agent based on explicit, deterministic conversation state
- Persistent memory with Postgres checkpoints (LangGraph `AsyncPostgresSaver`) and automatic context summarization
- Multi-channel: WhatsApp (Meta Cloud API), WhatsApp Calls, Twilio Voice + Deepgram, and a Chainlit web UI
- Cost controls: model router (Haiku for simple turns, Sonnet for complex ones), prompt compaction, per-turn usage metrics
- Lead capture, human handoff notifications and scheduled follow-ups
- One-command AWS deploys (CDK on ECS Fargate) with ops scripts for secrets, environments and sessions

---

## Architecture

```
WhatsApp / Twilio / Chainlit
        ↓
    FastAPI (api/)
        ↓
  AgentService  →  build_agent(client_config)
        ↓
MultiAgentSupervisor
        ↓
  ConversationState.choose_route()
        ↓
  Specialist Agent (LangGraph) → Bedrock (Claude)
        ↓
  Response back to the channel
```

### Per-turn flow

1. The channel calls its handler in `api/`
2. `AgentService` picks the model (Haiku by default, Sonnet for complex queries)
3. `MultiAgentSupervisor` loads the conversation history from the checkpoint (Postgres)
4. If there are 6+ messages and the stage changed, `context_refiner` writes a summary with Nova Lite
5. The client state (`ClientConfig.state_class`) decides the route (specialist)
6. The specialist writes the response with the client's prompts and tools

---

## Integrating with a client repo

Add the engine as a git submodule:

```bash
git submodule add git@github.com:GaboFrontDev/kaax-ai-core.git core
```

The client repo needs:

1. **`client.py`**: implements `build_client_config() -> ClientConfig`
2. **`main.py`**: sets the `ClientConfig` before importing the app:
   ```python
   sys.path.insert(0, str(Path(__file__).resolve().parent / "core"))
   from client import build_client_config
   from api.dependencies import set_client_config
   set_client_config(build_client_config())
   from api.main import app
   ```
3. **`states/`**: a `BaseConversationState` subclass with the funnel logic
4. **`tools/`**: client-specific tools
5. **`prompts/`**: prompt YAMLs; names must match what `choose_route()` returns
6. **`config.yaml`**: agent declaration (model, tools, prompts, tool_policy)

See [kaax-client](https://github.com/GaboFrontDev/kaax-client) for a reference implementation.

---

## Key files

| File | What it does |
|---|---|
| `agent.py` | `build_agent()`: entry point, returns a `MultiAgentSupervisor` |
| `multi_agent_supervisor.py` | Routing by funnel stage, memory injection |
| `base_conversation_state.py` | Abstract base class for client state |
| `client_config.py` | `ClientConfig` dataclass + `load_client_config()` from YAML |
| `api/agent_service.py` | Model router: Haiku by default, Sonnet for complex queries |
| `api/handlers.py` | `process_request`, `stream_request`, `stream_voice_sentences` |
| `api/dependencies.py` | `set_client_config()` / `get_client_config()` DI container |
| `api/routers/` | Channel endpoints (WhatsApp Meta, WhatsApp Calls, Twilio Voice), assist, admin, health |
| `infra/context_refiner.py` | Summarizes history with Nova Lite when the stage changes |
| `infra/model_router.py` | Haiku for simple messages, Sonnet for complex ones |
| `infra/follow_up/` | Conversation/memory DB helpers and the follow-up scheduler |
| `infra/handoff/` | Human handoff notifications |
| `session_manager.py` | Wrapper around `AsyncPostgresSaver` |
| `settings.py` | Environment variables with defaults |
| `prompt_factory.py` | Loads prompt YAMLs (from the client's `prompts/` or the engine's) |
| `infra/cdk/stacks/service_stack.py` | Generic CDK stack for ECS Fargate |
| `infra/cdk/app.py` | CDK app entry point; reads the client's `dockerfile_dir` from context |

---

## Local development (standalone)

To run the engine directly, without a client repo:

```bash
make sync
make docker-up    # local Postgres
make run-api
```

Optional:

```bash
make sync-channels && make run-chainlit   # Chainlit web UI
make health                               # GET /health
make assist                               # sample POST /api/agent/assist
```

Requires a `.env` at the repo root with at least:

```env
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres
API_TOKENS=dev-token
MULTI_AGENT_ENABLED=true
```

See `.env.example` for the full list.

---

## CDK deploy (from the client repo)

The CDK app lives in `infra/cdk/`. The client repo invokes it with `dockerfile_dir` so the image
is built from the client's root:

```bash
cd infra/cdk
cdk deploy \
  -c config=config/environments.json \
  -c env=dev \
  -c agent=default \
  -c dockerfile_dir=/path/to/client-repo
```

Client repos ship their own `ops/` scripts that do this automatically. The engine's `ops/` folder
includes scripts for bootstrap, deploy, diff, destroy, environment scaffolding, secrets sync and
session cleanup (also exposed as `make cdk-*` and `make session-clear*` targets).

### CDK context keys

| Key | Description |
|---|---|
| `config` | Path (relative to `cdk.json`) to `environments.json` |
| `env` | Environment name (dev, prod) |
| `agent` | Agent name (default, sales, …) |
| `dockerfile_dir` | Absolute path to the directory containing the `Dockerfile` |

---

## Cost optimization

| Flag | Default | Effect |
|---|---|---|
| `ENABLE_MODEL_ROUTER` | false | Haiku for simple messages, Sonnet for complex ones |
| `ENABLE_PROMPT_COMPACT` | false | Truncated input, reduced max_tokens |
| `ENABLE_USAGE_METRICS` | false | Writes to `llm_usage_events` on every turn |
| `MODEL_ROUTER_DEFAULT` | Haiku 4.5 | Cheap model |
| `MODEL_ROUTER_FALLBACK` | Sonnet 4.6 | Expensive model for complex queries |

---

## Migrations

```bash
uv run alembic upgrade head
```

Always migrate before deploying when there are new migrations in `migrations/versions/`.

---

## Tests

```bash
make test   # pytest
make lint   # ruff check
make fmt    # ruff format
```
