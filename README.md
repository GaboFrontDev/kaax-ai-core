# Core

Core aislado para construir agentes con LangChain/LangGraph + FastAPI, incluyendo:

- Patron `settings -> model_builder -> agent`.
- Modelo Bedrock.
- API principal (`/api/agent/assist`, `/health`).
- Checkpoints de LangGraph en PostgreSQL.
- Canal WhatsApp Meta (webhook verificacion + inbound/outbound).
- Capa Chainlit conectada al API.

## Estructura principal

- `settings.py`
- `model_builder.py`
- `agent.py`
- `tools/*`
- `prompts/agent.yaml`
- `session_manager.py`
- `sql_utilities.py`
- `api/*`
- `infra/whatsapp_meta/*`
- `infra/chainlit/*`

## Setup rapido

1. Copia `.env.example` a `.env` y completa credenciales.
2. Instala dependencias:

```bash
make sync
```

Si vas a usar Chainlit:

```bash
make sync-channels
```

## Correr servicios

API (FastAPI):

```bash
make run-api
```

Chainlit (UI local, conectada al API):

```bash
make run-chainlit
```

Para ocultar/mostrar eventos de tools en la UI:

```bash
make run-chainlit CHAINLIT_SHOW_TOOL_EVENTS=true
```

## Endpoints

- `GET /health`
- `POST /api/agent/assist`
- `GET /api/channels/whatsapp/meta/webhook` (verificacion Meta)
- `POST /api/channels/whatsapp/meta/webhook` (eventos inbound Meta)

## Variables clave de WhatsApp Meta

En `.env`:

- `WHATSAPP_META_VERIFY_TOKEN`
- `WHATSAPP_META_APP_SECRET`
- `WHATSAPP_META_ACCESS_TOKEN`
- `WHATSAPP_META_API_VERSION`
- `WHATSAPP_META_PHONE_NUMBER_ID`
- `WHATSAPP_META_PROMPT_NAME`
- `WHATSAPP_META_MODEL_NAME`
- `WHATSAPP_META_TEMPERATURE`

## Pruebas de humo

Health:

```bash
make health
```

Assist:

```bash
make assist
```

Verificacion webhook WhatsApp:

```bash
make webhook-verify WHATSAPP_VERIFY_TOKEN=<tu_token>
```
