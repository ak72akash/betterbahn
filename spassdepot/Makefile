# Spaßdepot – Entwicklungsbefehle
.PHONY: install dev backend frontend test lint typecheck demo

install:
	cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm ci

# Startet Backend (:8000) und Frontend (:5173) gemeinsam; Strg+C beendet beide.
dev:
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && npm test

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run lint

typecheck:
	cd backend && .venv/bin/mypy app
	cd frontend && npm run typecheck

# Beispieldaten in eine laufende, leere Instanz schreiben (am besten mit PROVIDER_ORDER=demo)
demo:
	cd backend && .venv/bin/python ../scripts/demo_daten.py
