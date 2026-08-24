PYTHON ?= .venv/Scripts/python.exe
MODELS_ENV ?= .env.models

.PHONY: test lint validate-dataset build-frontend validate-models pull-models up-models down-models smoke-llm smoke-llm-concurrent

test:
	$(PYTHON) -m pytest -q backend

lint:
	$(PYTHON) -m ruff check backend

validate-dataset:
	$(PYTHON) -m pytest -q backend/tests/test_catalog.py

build-frontend:
	npm --prefix frontend run build

validate-models:
	docker compose --env-file $(MODELS_ENV) --profile models config --quiet

pull-models:
	docker compose --env-file $(MODELS_ENV) --profile models pull vllm

up-models:
	docker compose --env-file $(MODELS_ENV) --profile models up -d vllm api frontend

down-models:
	docker compose --env-file $(MODELS_ENV) --profile models stop vllm

smoke-llm:
	$(PYTHON) backend/scripts/smoke_llm_profile.py

smoke-llm-concurrent:
	$(PYTHON) backend/scripts/smoke_llm_profile.py --concurrency 2
