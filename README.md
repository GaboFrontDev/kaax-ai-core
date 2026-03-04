# Core (Minimal)

Version minima aislada del proyecto original para crear agentes nuevos desde cero con:

- Patron `settings -> model_builder -> agent`
- Modelo Bedrock (sin Vertex/Chainlit)
- API FastAPI (`/api/agent/assist`, `/health`)
- Checkpoints de LangGraph en PostgreSQL
- 2 tools de ejemplo en el mismo formato del repo

## Estructura

- `core/settings.py`
- `core/model_builder.py`
- `core/agent.py`
- `core/tools/*`
- `core/prompts/agent.yaml`
- `core/session_manager.py`
- `core/sql_utilities.py`
- `core/api/*`

## Levantar API

1. Entra al modulo:

```bash
cd core
```

2. Copia `.env.example` a `.env` y completa credenciales.
   - Para checkpoints se usa `DATABASE_URL` directamente.
3. Instala dependencias del modulo:

```bash
uv sync
```

4. Ejecuta:

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Si tienes un `VIRTUAL_ENV` activo de otro proyecto, usa `uv run --active ...` o desactivalo antes.

## Request de ejemplo

```bash
curl -sS -X POST "http://127.0.0.1:8000/api/agent/assist" \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{
    "userText": "cuanto es 25 * 4?",
    "requestor": "local",
    "streamResponse": false
  }'
```
