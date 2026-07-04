# SelfAware — dev commands. Everything degrades: each target works (or fails
# honestly) without the others. `make demo-mock` needs NO hardware, NO API key,
# NO docker.

SHELL := /bin/bash
COMPOSE := docker compose -f infra/docker-compose.yml

# Load root .env into every target's environment when present.
-include .env
export

.PHONY: help infra-up infra-down dev-backend dev-frontend test typecheck demo-mock demo grafana

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

infra-up: ## start redis + agent-memory-server + grafana otel-lgtm
	$(COMPOSE) up -d --wait

infra-down: ## stop infra containers
	$(COMPOSE) down

dev-backend: ## run FastAPI with reload on :8000
	cd backend && uv run uvicorn selfaware.api.app:create_app --factory --reload --port 8000

dev-frontend: ## run Vite dev server on :5173
	cd frontend && npm run dev

test: ## backend tests — green with no .env, no docker, no USB, no API key
	cd backend && uv run pytest -q

typecheck: ## frontend type check
	cd frontend && npm run typecheck

demo-mock: ## full theater, zero hardware, zero cloud (MockBoard + canned author)
	cd backend && SELFAWARE_MOCK_BOARD=true SELFAWARE_MOCK_AUTHOR=true \
		uv run uvicorn selfaware.api.app:create_app --factory --port 8000

demo: ## demo-mock backend + frontend together
	$(MAKE) -j2 demo-mock dev-frontend

grafana: ## open the Grafana UI
	open http://localhost:3000
