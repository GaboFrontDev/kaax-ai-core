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
   Para crear un nuevo env/agent base automaticamente:

```bash
make cdk-init-env ENV=dev AGENT=clinicas DOMAIN=clinicas.kaax.ai
```

2. Exporta variables secretas requeridas en tu shell.
3. Sincroniza secretos y despliega:

```bash
make cdk-bootstrap
make cdk-sync-secrets CDK_SECRET_NAME=kaax/dev/default
make cdk-diff ENV=dev AGENT=default
make cdk-deploy ENV=dev AGENT=default
```

## Como desplegar un nuevo agente

Ejemplo: agente `clinicas` en `dev` con dominio `clinicas.kaax.ai`.

1. Crea el scaffold del agente en CDK:

```bash
make cdk-init-env ENV=dev AGENT=clinicas DOMAIN=clinicas.kaax.ai
```

2. Revisa `infra/cdk/config/environments.json` y confirma:
- `service_name` unico
- `secret_name` propio (ejemplo: `kaax/dev/clinicas`)
- `certificate_arn` valido para el subdominio
- `secret_keys` requeridos por el runtime que vas a usar

Ejemplo de bloque listo para pegar (solo cambia los placeholders):

```json
{
  "dev": {
    "account": "301782007691",
    "region": "us-east-1",
    "agents": {
      "clinicas": {
        "service_name": "kaax-dev-clinicas",
        "cpu": 512,
        "memory_mib": 1024,
        "cpu_architecture": "X86_64",
        "desired_count": 1,
        "min_capacity": 1,
        "max_capacity": 2,
        "container_port": 8200,
        "health_check_path": "/health/live",
        "deregistration_delay_seconds": 30,
        "public_load_balancer": true,
        "enable_https": true,
        "redirect_http": true,
        "certificate_arn": "<CAMBIAR_ACM_CERT_ARN>",
        "public_base_url": "https://clinicas.kaax.ai",
        "environment": {
          "AUDRAI_DEPLOY_ENV": "dev",
          "AGENT_RUNTIME_BACKEND": "langgraph_mvp",
          "CHECKPOINT_BACKEND": "postgres",
          "CRM_BACKEND": "postgres",
          "INTERACTION_METRICS_BACKEND": "postgres",
          "KNOWLEDGE_BACKEND": "postgres",
          "KNOWLEDGE_TABLE_NAME": "agent_knowledge",
          "LOG_FORMAT": "json",
          "LOG_LEVEL": "INFO",
          "MULTI_AGENT_ENABLED": "true",
          "DEMO_LINK": "<CAMBIAR_LINK_DEMO>",
          "PRICING_LINK": "<CAMBIAR_LINK_PRECIOS>",
          "WHATSAPP_NOTIFY_TO": "<CAMBIAR_NUMERO_DESTINO>"
        },
        "secret_name": "kaax/dev/clinicas",
        "secret_keys": [
          "API_TOKENS",
          "DATABASE_URL",
          "AWS_REGION",
          "BEDROCK_MODEL",
          "DEFAULT_PROMPT_NAME",
          "WHATSAPP_META_VERIFY_TOKEN",
          "WHATSAPP_META_APP_SECRET",
          "WHATSAPP_META_ACCESS_TOKEN",
          "WHATSAPP_META_PHONE_NUMBER_ID"
        ]
      }
    }
  }
}
```

3. Sincroniza secretos al secret nuevo:

```bash
make cdk-sync-secrets CDK_SECRET_NAME=kaax/dev/clinicas
```

4. Previsualiza cambios:

```bash
make cdk-diff ENV=dev AGENT=clinicas
```

5. Despliega:

```bash
make cdk-deploy ENV=dev AGENT=clinicas
```

6. Obtén valores DNS para tu gestor de dominio:

```bash
make cdk-dns-config ENV=dev AGENT=clinicas DOMAIN=clinicas.kaax.ai
```

7. Verifica salud del nuevo agente:

```bash
make awsctl AWSCTL_ARGS="health dev clinicas"
```

## Consideraciones

- Cada `AGENT` despliega stack y servicio ECS independientes (`Kaax-<env>-<agent>`).
- Usa `secret_name` separado por agente para evitar colisiones de credenciales.
- No dependas de keys legacy (`DB_DSN`, `MODEL_NAME`, `SMALL_MODEL`, `PHONE_NUMBER_ID`) en nuevos agentes.
- Si activas HTTPS (`enable_https=true`), el `certificate_arn` debe cubrir el dominio final.
- `public_base_url` no crea DNS automaticamente; debes crear el CNAME en tu proveedor.
- Si usas voz/calls, agrega tambien `TWILIO_VOICE_AUTH_TOKEN`, `TWILIO_ACCOUNT_SID`, `DEEPGRAM_KEY`.
- El primer deploy puede tardar mas por build y push de imagen.
- Si hay rollback en progreso, espera `UPDATE_ROLLBACK_COMPLETE` antes de redeploy.
