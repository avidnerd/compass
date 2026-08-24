PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: setup migrate dev test build serve backend-dev frontend-dev

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -r backend/requirements.txt
	cd frontend && (npm ci 2>/dev/null || npm install)

migrate:
	cd backend && ../$(PY) migrate.py

dev:
	@trap 'kill 0' EXIT INT TERM; \
	( cd backend && ../$(PY) -m uvicorn app.main:app --reload --host $${COMPASS_BIND_HOST:-127.0.0.1} --port 8000 ) & \
	( cd frontend && npm run dev ) & \
	wait

test:
	cd backend && ../$(PY) -m pytest tests -q
	cd frontend && npx tsc -b && npm run lint

build:
	cd frontend && npm run lint && npm run build
	cd backend && ../$(PY) -m pytest tests -q

serve:
	cd backend && ../$(PY) -m uvicorn app.main:app --host $${COMPASS_BIND_HOST:-127.0.0.1} --port 8000
