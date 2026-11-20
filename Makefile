.DEFAULT_GOAL := help
PY ?= .venv/bin/python
BACKEND_DIR := backend

help:  ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[33m%-16s\033[0m %s\n", $$1, $$2}'

setup:  ## Crea .venv e instala ml + backend + frontend
	python3 -m venv .venv
	.venv/bin/pip install -e "ml[etl,dev,nlp]" -e "backend[dev]"
	cd frontend && npm ci

migrate:  ## Aplica migraciones (SQLite local por defecto)
	cd $(BACKEND_DIR) && ../$(PY) -m alembic upgrade head

seed:  ## Carga/actualiza el catálogo (Gold ETL + LIDER) en la BD
	cd $(BACKEND_DIR) && ../$(PY) -m app.cli seed

dev-backend: migrate seed  ## API en http://localhost:8000 (docs en /api/docs)
	cd $(BACKEND_DIR) && ADMIN_PASSWORD=$${ADMIN_PASSWORD:-admin} ../.venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:  ## UI en http://localhost:5173 (proxy /api -> :8000)
	cd frontend && npm run dev

test:  ## Pruebas de ml, backend y frontend
	cd ml && ../$(PY) -m pytest -q
	cd $(BACKEND_DIR) && ../$(PY) -m pytest -q
	cd frontend && npm test

lint:  ## ruff + tipos del frontend
	cd $(BACKEND_DIR) && ../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .
	cd frontend && npm run typecheck

migration:  ## Genera una migración: make migration m="descripcion"
	cd $(BACKEND_DIR) && ../$(PY) -m alembic revision --autogenerate -m "$(m)"

up:  ## Stack completo con Docker en http://localhost:8080
	docker compose up --build -d

down:  ## Detiene el stack Docker (conserva la BD)
	docker compose down

logs:  ## Logs del stack Docker
	docker compose logs -f --tail=100

.PHONY: help setup migrate seed dev-backend dev-frontend test lint migration up down logs
