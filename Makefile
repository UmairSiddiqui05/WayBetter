# WayBetter task runner.
# `make help` lists everything. Fresh clone: `make env && make up`.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
PYTHON ?= python3.12
VENV := $(CURDIR)/backend/.venv
VENV_BIN := $(VENV)/bin
API_URL ?= http://localhost:8000

.PHONY: help
help: ## List available targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------

.PHONY: env
env: ## Create .env from the template if it does not exist
	@if [ -f .env ]; then \
		echo ".env already exists — left untouched."; \
	else \
		cp .env.example .env; \
		echo "Created .env from .env.example. Edit it before running anything paid."; \
	fi

$(VENV_BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install --upgrade pip

.PHONY: install
install: $(VENV_BIN)/python ## Install backend deps into backend/.venv
	$(VENV_BIN)/pip install -e "backend[dev]"

# --- Docker stack ------------------------------------------------------------

.PHONY: up
up: env ## Build and start api + db (PostGIS) + redis
	$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory wait-ready

.PHONY: up-otp
up-otp: env ## Also start OpenTripPlanner (needs a graph bundle in data/otp-graphs/current)
	@if [ ! -d data/otp-graphs/current ]; then \
		echo "data/otp-graphs/current is missing — build a graph bundle first (A2)."; exit 1; \
	fi
	$(COMPOSE) --profile otp up -d --build

.PHONY: down
down: ## Stop the stack (keeps volumes)
	$(COMPOSE) --profile otp down

.PHONY: clean
clean: ## Stop the stack and delete its volumes (destroys local database)
	$(COMPOSE) --profile otp down --volumes

.PHONY: ps
ps: ## Show container status
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail logs (make logs SERVICE=api)
	$(COMPOSE) logs -f $(SERVICE)

.PHONY: wait-ready
wait-ready: ## Poll /readyz until the API reports every required component up
	@echo "Waiting for $(API_URL)/readyz ..."
	@for i in $$(seq 1 60); do \
		if curl -sf $(API_URL)/readyz > /dev/null; then \
			curl -s $(API_URL)/readyz; echo; echo "Stack is ready."; exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "Timed out. Last response:"; curl -s $(API_URL)/readyz; echo; \
	$(COMPOSE) ps; exit 1

.PHONY: shell
shell: ## Shell into the api container
	$(COMPOSE) exec api /bin/bash

.PHONY: psql
psql: ## Open psql against the local database
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-waybetter} -d $${POSTGRES_DB:-waybetter}

.PHONY: postgis-version
postgis-version: ## Print the PostGIS version the database reports
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-waybetter} -d $${POSTGRES_DB:-waybetter} \
		-tAc "SELECT 'PostGIS ' || extversion FROM pg_extension WHERE extname = 'postgis'"

# --- Backend checks (run on the host; no datastores required) ----------------

.PHONY: lint
lint: install ## ruff lint + format check
	cd backend && $(VENV_BIN)/ruff check . && $(VENV_BIN)/ruff format --check .

.PHONY: fmt
fmt: install ## Apply ruff formatting and safe fixes
	cd backend && $(VENV_BIN)/ruff check --fix . && $(VENV_BIN)/ruff format .

.PHONY: typecheck
typecheck: install ## mypy (strict)
	cd backend && $(VENV_BIN)/mypy

.PHONY: test
test: install ## pytest
	cd backend && ENVIRONMENT=test $(VENV_BIN)/pytest -q

.PHONY: check
check: lint typecheck test ## Everything CI runs for the backend

.PHONY: openapi
openapi: install ## Print the generated OpenAPI document
	cd backend && $(VENV_BIN)/python -c \
		"import json; from app.main import create_app; print(json.dumps(create_app().openapi(), indent=2))"

.PHONY: contract-lint
contract-lint: ## Lint the API contract the way CI does
	npx --yes @redocly/cli@latest lint docs/api-spec.yaml
