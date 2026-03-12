# Core Engine

Engine genérico para construir agentes conversacionales con LangGraph + FastAPI + AWS Bedrock.

Diseñado para correr como submódulo dentro de un **repo cliente** que aporta la lógica específica
del negocio (prompts, tools, estado del funnel). El engine no sabe nada del cliente — recibe un
`ClientConfig` al arrancar y lo usa para todo.

---

## Arquitectura

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
  Respuesta al canal
```

### Flujo por turno

1. El canal llama al handler correspondiente en `api/`
2. `AgentService` decide modelo (Haiku default, Sonnet para queries complejas)
3. `MultiAgentSupervisor` carga historial del checkpoint (Postgres)
4. Si hay >= 6 mensajes y la etapa cambio → `context_refiner` genera resumen con Nova Lite
5. El estado del cliente (`ClientConfig.state_class`) determina la ruta (specialist)
6. El specialist genera la respuesta con los prompts y tools del cliente

---

## Integracion con un repo cliente

El engine se incluye como submodulo de git:

```bash
git submodule add git@github.com:GaboFrontDev/kaax-ai-core.git core
```

El repo cliente necesita:

1. **`client.py`** — implementa `build_client_config() -> ClientConfig`
2. **`main.py`** — monta el `ClientConfig` antes de importar el app:
   ```python
   sys.path.insert(0, str(Path(__file__).resolve().parent / "core"))
   from client import build_client_config
   from api.dependencies import set_client_config
   set_client_config(build_client_config())
   from api.main import app
   ```
3. **`states/`** — subclase de `BaseConversationState` con la logica del funnel
4. **`tools/`** — tools especificas del cliente
5. **`prompts/`** — YAMLs de prompts; los nombres deben coincidir con lo que retorna `choose_route()`
6. **`config.yaml`** — declaracion del agente (modelo, tools, prompts, tool_policy)

Ver [kaax-client](https://github.com/GaboFrontDev/kaax-client) como ejemplo de implementacion.

---

## Archivos clave

| Archivo | Que hace |
|---|---|
| `agent.py` | `build_agent()` — entry point, devuelve `MultiAgentSupervisor` |
| `multi_agent_supervisor.py` | Routing por etapa del funnel, inyeccion de memoria |
| `base_conversation_state.py` | Clase base abstracta para el estado del cliente |
| `client_config.py` | `ClientConfig` dataclass + `load_client_config()` desde YAML |
| `api/agent_service.py` | Model router: Haiku default, Sonnet para queries complejas |
| `api/handlers.py` | `process_request`, `stream_request`, `stream_voice_sentences` |
| `api/dependencies.py` | `set_client_config()` / `get_client_config()` DI container |
| `infra/context_refiner.py` | Resumen de historial con Nova Lite al cambiar etapa |
| `infra/model_router.py` | Haiku para msgs simples, Sonnet para complejos |
| `session_manager.py` | Wrapper sobre `AsyncPostgresSaver` |
| `settings.py` | Variables de entorno con defaults |
| `prompt_factory.py` | Carga YAMLs de prompts (desde `prompts/` del cliente o del engine) |
| `infra/cdk/stacks/service_stack.py` | CDK stack generico para ECS Fargate |
| `infra/cdk/app.py` | CDK app entry point — lee `dockerfile_dir` del cliente via context |

---

## Desarrollo local (standalone)

Para correr el engine directamente sin repo cliente:

```bash
make sync
make docker-up    # Postgres local
make run-api
```

Requiere un `.env` en la raiz con al menos:

```env
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres
API_TOKENS=dev-token
MULTI_AGENT_ENABLED=true
```

---

## Deploy CDK (desde el repo cliente)

El CDK esta en `infra/cdk/`. El repo cliente lo invoca pasando `dockerfile_dir` para que
la imagen se construya desde la raiz del cliente:

```bash
cd infra/cdk
cdk deploy \
  -c config=config/environments.json \
  -c env=dev \
  -c agent=default \
  -c dockerfile_dir=/ruta/al/repo-cliente
```

Los repos clientes tienen sus propios scripts en `ops/` que hacen esto automaticamente.

### Context keys de CDK

| Key | Descripcion |
|---|---|
| `config` | Path relativo (desde `cdk.json`) a `environments.json` |
| `env` | Nombre del entorno (dev, prod) |
| `agent` | Nombre del agente (default, sales, …) |
| `dockerfile_dir` | Ruta absoluta al directorio con el `Dockerfile` |

---

## Cost optimization

| Flag | Default | Efecto |
|---|---|---|
| `ENABLE_MODEL_ROUTER` | false | Haiku para msgs simples, Sonnet para complejos |
| `ENABLE_PROMPT_COMPACT` | false | Input truncado, max_tokens reducido |
| `ENABLE_USAGE_METRICS` | false | Escribe a `llm_usage_events` por turno |
| `MODEL_ROUTER_DEFAULT` | Haiku 4.5 | Modelo barato |
| `MODEL_ROUTER_FALLBACK` | Sonnet 4.6 | Modelo caro para queries complejas |

---

## Migraciones

```bash
uv run alembic upgrade head
```

Siempre migrar antes de deployar cuando hay migraciones nuevas en `migrations/versions/`.

---

## Tests

```bash
make test   # pytest
make lint   # ruff check
make fmt    # ruff format
```
