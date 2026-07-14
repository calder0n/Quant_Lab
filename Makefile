.PHONY: up down build logs ps test test-integration lint fmt typecheck check migrate revision

up: ## Start the full stack
	docker compose up -d --build

down: ## Stop the stack (data volumes are preserved)
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

test: ## Unit tests + coverage gate (>=90%)
	docker compose run --rm --no-deps api pytest

test-integration: ## Full suite including live-service tests
	docker compose run --rm -e QL_INTEGRATION=1 api pytest

lint:
	docker compose run --rm --no-deps api ruff check src tests
	docker compose run --rm --no-deps api black --check src tests

typecheck:
	docker compose run --rm --no-deps api mypy

fmt:
	docker compose run --rm --no-deps api black src tests
	docker compose run --rm --no-deps api ruff check --fix src tests

check: lint typecheck test ## Everything the CI would run

migrate: ## Apply database migrations
	docker compose run --rm api alembic upgrade head

revision: ## Autogenerate a migration: make revision m="message"
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"
