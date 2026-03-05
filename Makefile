SERVER_PORT ?= 8200
HOST ?= 0.0.0.0
API_BASE_URL ?= http://127.0.0.1:$(SERVER_PORT)
API_TOKEN ?= dev-token

CHAINLIT_PORT ?= 8300
CHAINLIT_API_URL ?= $(API_BASE_URL)
CHAINLIT_API_TOKEN ?= $(API_TOKEN)
CHAINLIT_SHOW_TOOL_EVENTS ?= true

WHATSAPP_WEBHOOK_URL ?= $(API_BASE_URL)/api/channels/whatsapp/meta/webhook
WHATSAPP_VERIFY_TOKEN ?= dev-whatsapp-verify-token

ENV ?= dev
AGENT ?= default
AWSCTL_ARGS ?= help
SESSION_ID ?=

.PHONY: help \
	sync sync-dev sync-channels \
	run-api run-api-prod run-chainlit \
	health assist webhook-verify \
	test lint fmt \
	docker-up docker-down docker-logs docker-up-redis docker-test-postgres docker-test-redis \
	cdk-bootstrap cdk-deploy cdk-diff cdk-destroy cdk-cancel cdk-sync-secrets awsctl \
	session-clear

help:
	@echo "Targets disponibles:"
	@echo "  make sync               -> instala dependencias base"
	@echo "  make sync-dev           -> instala dependencias base + dev"
	@echo "  make sync-channels      -> instala dependencias base + dev + chainlit"
	@echo "  make run-api            -> levanta FastAPI en modo reload"
	@echo "  make run-chainlit       -> levanta UI Chainlit conectada al API"
	@echo "  make health             -> prueba GET /health"
	@echo "  make assist             -> prueba POST /api/agent/assist"
	@echo "  make webhook-verify     -> prueba verificacion de webhook WhatsApp"
	@echo "  make test lint fmt      -> calidad de codigo"
	@echo "  make docker-up/down     -> postgres local (compose)"
	@echo "  make docker-up-redis    -> redis + sentinel local (compose)"
	@echo "  make cdk-cancel         -> cancela un update de CloudFormation en progreso"
	@echo "  make cdk-logs           -> sigue los logs del contenedor en ECS en tiempo real"
	@echo "  make session-clear      -> elimina memoria/checkpoints de un sessionId (SESSION_ID=...)"

sync:
	uv sync

sync-dev:
	uv sync --group dev

sync-channels:
	uv sync --group dev --group channels

run-api:
	uv run uvicorn api.main:app --host $(HOST) --port $(SERVER_PORT) --reload

run-api-prod:
	uv run uvicorn api.main:app --host $(HOST) --port $(SERVER_PORT)

run-chainlit:
	CHAINLIT_API_URL=$(CHAINLIT_API_URL) \
	CHAINLIT_API_TOKEN=$(CHAINLIT_API_TOKEN) \
	CHAINLIT_SHOW_TOOL_EVENTS=$(CHAINLIT_SHOW_TOOL_EVENTS) \
	DATABASE_URL= \
	LITERAL_API_KEY= \
	PYTHONPATH=$(CURDIR) \
	uv run --group channels chainlit run infra/chainlit/app.py -w --port $(CHAINLIT_PORT)

health:
	curl -sS -m 3 "$(API_BASE_URL)/health"

assist:
	curl -sS -X POST "$(API_BASE_URL)/api/agent/assist" \
		-H "Authorization: Bearer $(API_TOKEN)" \
		-H "Content-Type: application/json" \
		-d '{"userText":"cuanto es 25 * 4?","requestor":"local","streamResponse":false}'

webhook-verify:
	curl -sS "$(WHATSAPP_WEBHOOK_URL)?hub.mode=subscribe&hub.verify_token=$(WHATSAPP_VERIFY_TOKEN)&hub.challenge=ok"

test:
	uv run --group dev pytest

lint:
	uv run --group dev ruff check .

fmt:
	uv run --group dev ruff format .

docker-up:
	docker compose up -d postgres

docker-up-redis:
	docker compose up -d redis-master redis-sentinel-1 redis-sentinel-2 redis-sentinel-3

docker-down:
	docker compose down -v

docker-logs:
	docker compose logs --tail=200

docker-test-postgres: docker-up
	@echo "Waiting for postgres healthcheck..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' kaaxai-postgres 2>/dev/null)" = "healthy" ]; do sleep 1; done
	@DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres \
		uv run python -c "import asyncio; from sql_utilities import test_database_connection_async; print(asyncio.run(test_database_connection_async()))"

docker-test-redis: docker-up-redis
	@echo "Waiting for redis sentinels healthcheck..."
	@for svc in kaaxai-redis-sentinel-1 kaaxai-redis-sentinel-2 kaaxai-redis-sentinel-3; do \
		ok=0; \
		for i in $$(seq 1 60); do \
			status=$$(docker inspect -f '{{.State.Health.Status}}' $$svc 2>/dev/null || echo "missing"); \
			if [ "$$status" = "healthy" ]; then \
				ok=1; \
				break; \
			fi; \
			sleep 1; \
		done; \
		if [ "$$ok" -ne 1 ]; then \
			echo "$$svc did not become healthy in time"; \
			docker compose logs --tail=200 redis-master redis-sentinel-1 redis-sentinel-2 redis-sentinel-3; \
			exit 1; \
		fi; \
	done
	@echo "Redis Sentinel cluster healthy"

cdk-bootstrap:
	./ops/bootstrap.sh

cdk-deploy:
	./ops/deploy.sh $(ENV) $(AGENT)

cdk-diff:
	./ops/diff.sh $(ENV) $(AGENT)

cdk-destroy:
	./ops/destroy.sh $(ENV) $(AGENT)

cdk-cancel:
	./ops/awsctl.sh cancel $(ENV) $(AGENT)

cdk-logs:
	@LOG_GROUP=$$(aws logs describe-log-groups \
		--region us-east-1 \
		--query "logGroups[?contains(logGroupName,'kaax-$(ENV)')].logGroupName | [0]" \
		--output text 2>/dev/null); \
	if [ -z "$$LOG_GROUP" ] || [ "$$LOG_GROUP" = "None" ]; then \
		LOG_GROUP=$$(aws logs describe-log-groups \
			--region us-east-1 \
			--query "logGroups[?contains(logGroupName,'Kaax')].logGroupName | [0]" \
			--output text); \
	fi; \
	echo "Log group: $$LOG_GROUP"; \
	aws logs tail "$$LOG_GROUP" --follow --region us-east-1 --format short

cdk-sync-secrets:
	@set -a; \
	if [ -f ./.env ]; then . ./.env; fi; \
	if [ -f ./.env.local ]; then . ./.env.local; fi; \
	set +a; \
	./ops/secrets-sync.sh $(CDK_SECRET_NAME)

awsctl:
	./ops/awsctl.sh $(AWSCTL_ARGS)

session-clear:
	./ops/session-clear.sh "$(SESSION_ID)"
