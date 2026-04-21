# Kaax AI Core — Guía para Claude

## ¿Qué es este repo?

Kaax AI es una plataforma de agentes de ventas conversacionales por WhatsApp para empresas B2B en México/LATAM. Este repositorio es el **backend del agente** — expone una API FastAPI que recibe mensajes de WhatsApp (Meta), los procesa con LangGraph + AWS Bedrock, y responde en lenguaje natural.

**Producto**: agente de ventas conversacional que califica prospectos (BANT), agenda demos y captura leads.
**Canal principal**: WhatsApp Business.
**Precio**: $18,000 MXN/mes por cliente. Cada cliente tiene su propio deploy aislado.
**Stack**: Python + LangGraph + AWS Bedrock (Claude Sonnet/Haiku) + Postgres (Supabase).

---

## Arquitectura

```
WhatsApp → FastAPI → MultiAgentSupervisor → LangGraph agent → Bedrock (Claude)
                          ↓
                  ConversationState (funnel BANT)
                          ↓
              discovery / qualification / capture / knowledge
```

### Flujo por turno
1. `whatsapp_meta.py` recibe el mensaje, llama `upsert_conversation()`
2. `AgentService.create_agent_for_request()` decide modelo (model router: Haiku default, Sonnet fallback)
3. `MultiAgentSupervisor._build_specialist_agent()`:
   - Carga historial del checkpoint (Postgres)
   - Si hay ≥ 6 mensajes y etapa cambió → `context_refiner` genera resumen con Nova Lite
   - Inyecta resumen en system prompt
   - Elige ruta: discovery / qualification / capture / knowledge
4. Specialist agent genera respuesta con Sonnet o Haiku
5. Respuesta enviada de vuelta por WhatsApp

---

## Archivos clave

| Archivo | Qué hace |
|---|---|
| `agent.py` | `build_agent()` — entry point, devuelve MultiAgentSupervisor o agente legacy |
| `multi_agent_supervisor.py` | Routing por etapa del funnel, inyección de memoria |
| `conversation_state.py` | Estado determinístico del funnel (etapa, volumen, intención) |
| `api/agent_service.py` | Model router: Haiku default, Sonnet para queries complejas |
| `api/handlers.py` | `process_request`, `stream_request`, `stream_voice_sentences` |
| `infra/context_refiner.py` | Genera resumen compacto con Nova Lite cuando etapa cambia |
| `infra/follow_up/db.py` | Helpers DB: conversations, memory, follow-ups |
| `infra/follow_up/scheduler.py` | Cron cada 30 min: manda follow-up a los 2 horas si no hay demo |
| `infra/model_router.py` | Haiku para mensajes simples, Sonnet para complejos |
| `settings.py` | Todas las variables de entorno con defaults |
| `prompts/` | YAMLs por agente especialista |
| `migrations/` | Alembic migrations (correr con `uv run alembic upgrade head`) |
| `infra/cdk/config/environments.json` | Config de deploy por entorno (dev/prod) |

---

## Prompts

| Prompt | Cuándo aplica |
|---|---|
| `shared_base.yaml` | Base de todos los agentes (tono, reglas globales) |
| `discovery_agent.yaml` | Primer contacto: obtiene negocio, producto, volumen, canal |
| `qualification_agent.yaml` | Muestra valor según volumen (fuerte vs en_desarrollo) |
| `capture_agent.yaml` | Captura datos de contacto y ofrece demo |
| `knowledge_agent.yaml` | Responde preguntas de precios, implementación, capacidades |
| `voice_agent.yaml` | Voz (Twilio + Deepgram) |

---

## Cost optimization (activo en prod)

| Flag | Valor | Efecto |
|---|---|---|
| `ENABLE_MODEL_ROUTER` | true | Haiku para msgs simples, Sonnet para complejos |
| `ENABLE_PROMPT_COMPACT` | true | Sin tool round-trip, input truncado, max_tokens=320 |
| `ENABLE_USAGE_METRICS` | true | Escribe a `llm_usage_events` por cada turno |
| `ENABLE_HISTORY_COMPRESSION` | false | Desactivado (usar context_refiner en su lugar) |
| `MODEL_ROUTER_DEFAULT` | Haiku 4.5 | Modelo barato para msgs simples |
| `MODEL_ROUTER_FALLBACK` | Sonnet 4.6 | Modelo caro para queries complejas |

**Ahorro estimado**: ~81% vs el setup original (Sonnet × 2 llamadas por mensaje).

---

## Reglas de negocio importantes

- `en_desarrollo` = volumen < 20 msgs/día → NO ofrecer demo proactivamente
- `fuerte` = volumen ≥ 20 msgs/día → sí ofrecer demo
- Intención solo sube (baja → media → alta), nunca baja
- Opciones 1-4 del menú nunca se parsean como volumen
- Follow-up solo se manda una vez, 2 horas después del último mensaje, si no hay demo solicitada

---

## Principios de solución

- El enfoque por defecto para cambios conversacionales debe seguir el flow de LangGraph.
- Priorizar `StateGraph`, estado explícito, rutas condicionales y salidas estructuradas sobre lógica pegada al router o al borde.
- Priorizar decisiones semánticas basadas en estado, contexto e intención sobre heurísticas frágiles como listas de frases o strings exactos.
- Usar listas de frases o matching literal solo como último recurso para integraciones de borde, compatibilidad o failsafes muy concretos.
- Cuando un comportamiento sea parte del negocio conversacional (handoff, routing, escalación, recovery, etc.), debe modelarse dentro del flujo del grafo y no como post-procesamiento superficial de mensajes.

---

## Deploy

```bash
# 1. Migrar DB (solo cuando hay migraciones nuevas)
uv run alembic upgrade head

# 2. Deploy CDK
cd infra/cdk && cdk deploy
```

La DB (Supabase) es independiente del deploy — migrar primero siempre es seguro.

---

## Visión a futuro

Este codebase está pensado para ser la **plataforma** sobre la que corren N agentes de clientes (tiendas, servicios, empresas). Cada cliente tiene su deploy aislado con su propio WhatsApp, DB y configuración. El funnel de ventas es genérico — lo que cambia por cliente son los prompts y el conocimiento del negocio.

Próximo paso: abstraer el supervisor para que sea configurable por cliente via YAML, sin tocar código.
