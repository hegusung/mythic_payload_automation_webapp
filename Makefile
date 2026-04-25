.PHONY: up down build logs restart dev

## Start the app (build if needed)
up:
	docker compose up --build -d
	@echo ""
	@echo "  ✓ App running → http://localhost:7080"
	@echo "  ✓ API         → http://localhost:7081/api"
	@echo ""

## Stop
down:
	docker compose down

## Rebuild images without cache
build:
	docker compose build --no-cache

## Follow logs
logs:
	docker compose logs -f

## Restart
restart:
	docker compose restart

## Local dev (no Docker)
dev:
	@echo "Starting backend..."
	@cd backend && (source .venv/bin/activate 2>/dev/null || python3 -m venv .venv && source .venv/bin/activate && pip install -q -r requirements.txt) && \
		PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
	@echo "Starting frontend..."
	@cd frontend && npm install && npm run dev
