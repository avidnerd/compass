PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: setup migrate dev test build serve backend-dev frontend-dev package

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

# Assemble an installable wheel: build the SPA, copy it inside the package so an
# installed copy has an interface to serve, then build with hatchling.
package:
	cd frontend && npm run build
	rm -rf backend/app/web && cp -R frontend/dist backend/app/web
	cd backend && ../$(PY) -m pip install --quiet --upgrade build hatchling
	cd backend && ../$(PY) -m build --wheel
	@echo
	@echo "Wheel in backend/dist/. Install it anywhere with:"
	@echo "  uv tool install ./backend/dist/*.whl     # or: pipx install ./backend/dist/*.whl"
	@echo "Then run:  compass"
