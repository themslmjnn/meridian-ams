# Start the full stack (builds image if needed)
up:
	docker compose up --build

# Stop and remove containers (preserves volumes)
down:
	docker compose down

# Run Alembic migrations inside the running app container
migrate:
	docker compose exec app uv run alembic upgrade head

# Tail app container logs
logs:
	docker compose logs -f app

# Run the full test suite
test:
	uv run pytest $(ARGS)

# Open a shell inside the running app container
shell:
	docker compose exec app /bin/bash

# Format source and tests with Ruff
format:
	uv run ruff format .

# Lint source and tests with Ruff
lint:
	uv run ruff check .

# Type-check with mypy
typecheck:
	uv run mypy src/

# Audit dependencies for known vulnerabilities
audit:
	uv run pip-audit

# Install all dependencies including dev extras (for local development without Docker)
install:
	uv sync --all-extras