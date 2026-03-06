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
- `infra/adapters/*` (selector de adapters por canal/proveedor)
- `infra/deepgram/*` (cliente compartido STT/TTS)
- `infra/whatsapp_calls/*` (wrappers de Deepgram para llamadas WhatsApp/WebRTC)
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
- `GET /health/live`
- `POST /api/agent/assist`
- `GET /api/channels/whatsapp/meta/webhook` (verificacion Meta)
- `POST /api/channels/whatsapp/meta/webhook` (eventos inbound Meta)
- `GET /api/channels/whatsapp/meta/calls` (verificacion webhook de llamadas)
- `POST /api/channels/whatsapp/meta/calls` (eventos de WhatsApp Calling)
- `GET /calls` (alias de verificacion para suscriptor de llamadas)
- `POST /calls` (alias de eventos para suscriptor de llamadas)

## Variables clave de WhatsApp Meta

En `.env`:

- `WHATSAPP_PROVIDER` (default: `meta`)
- `WHATSAPP_META_VERIFY_TOKEN`
- `WHATSAPP_META_APP_SECRET`
- `WHATSAPP_META_ACCESS_TOKEN`
- `WHATSAPP_META_API_VERSION`
- `WHATSAPP_META_PHONE_NUMBER_ID`
- `WHATSAPP_META_PROMPT_NAME`
- `WHATSAPP_META_MODEL_NAME`
- `WHATSAPP_META_TEMPERATURE`

## Variables clave de Voice

En `.env`:

- `VOICE_PROVIDER` (default: `twilio`)
- `TWILIO_VOICE_AUTH_TOKEN`
- `TWILIO_VOICE_BASE_URL`
- `TWILIO_VOICE_PROMPT_NAME`
- `TWILIO_VOICE_MODEL_NAME`
- `TWILIO_VOICE_TEMPERATURE`

## Variables clave de WhatsApp Calling

En `.env`:

- `WHATSAPP_CALLS_VERIFY_TOKEN` (si está vacío usa `WHATSAPP_META_VERIFY_TOKEN`)
- `WHATSAPP_CALLS_APP_SECRET` (si está vacío usa `WHATSAPP_META_APP_SECRET`)
- `WHATSAPP_CALLS_PROMPT_NAME` (default: `voice_agent`)
- `WHATSAPP_CALLS_MODEL_NAME`
- `WHATSAPP_CALLS_TEMPERATURE`
- `WHATSAPP_CALLS_INCLUDE_TTS_PAYLOAD` (debug, default: `false`)

Nota: para negociación SDP/WebRTC (`answer` en `POST /calls`) necesitas instalar `aiortc`.

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

## Deploy AWS (CDK)

1. Ajusta `infra/cdk/config/environments.json`.
2. Exporta variables secretas requeridas en tu shell.
3. Sincroniza secretos y despliega:

```bash
make cdk-bootstrap
make cdk-sync-secrets CDK_SECRET_NAME=kaax/dev/default
make cdk-diff ENV=dev AGENT=default
make cdk-deploy ENV=dev AGENT=default
```
