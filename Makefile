.PHONY: up down logs test lint proto migrate migrate-check migrate-new clean help

up:
	docker-compose up -d
down:
	docker-compose down
## Tail logs for all services
logs:
	docker-compose logs -f --tail=50

## Start monitoring stack (Prometheus + Grafana + Alertmanager)
up-monitoring:
	docker-compose --profile monitoring up -d
## Run Alembic migrations to head
migrate:
	cd control && alembic upgrade head

## Check current DB revision
migrate-check:
	cd control && alembic current

## Create a new migration (usage: make migrate-new MSG="add foo column")
migrate-new:
	cd control && alembic revision --autogenerate -m "$(MSG)"
## Show migration history
migrate-history:
	cd control && alembic history --verbose
## Regenerate protobuf Python files
proto:
	cd walstream-proto && python -m walstream_proto.generate

test:
	pytest --tb=short -q

test-cov:
	pytest --cov=control --cov=ingestor --cov=replayer --tb=short

## Run proto compatibility tests
test-proto:
	pytest walstream-proto/tests/ --tb=short -q

## Run delivery-semantics focused tests
test-delivery:
	pytest -k "delivery or dedup or idempoten" --tb=short -q

lint:
	ruff check .

fmt:
	ruff format .

typecheck:
	mypy control/ ingestor/ replayer/

check: lint typecheck

dev-control:
	cd control && uvicorn app.main:app --reload --port 8000

dev-ingestor:
	python ingestor/ingestor.py

dev-replayer:
	python replayer/server.py

dev-frontend:
	cd frontend && npm run dev

## Remove Python caches and build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

## Remove Docker volumes (DESTRUCTIVE)
clean-volumes:
	docker-compose down -v

help:
	@echo "WalStream CDC - Available targets:"
	@echo ""
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
	@echo ""
	@echo "Run 'make <target>' to execute."
