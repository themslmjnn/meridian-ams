.PHONY: dev format migrate migration autogenerate test cov cov-html

dev:
	uv run uvicorn meridian_ams.main:app --reload

format:
	uv run ruff format .

migrate:
	uv run alembic upgrade head

migration:
	@test -n "$(m)" || (echo 'usage: make migration m="message"'; exit 1)
	uv run alembic revision -m "$(m)"

mig-auto:
	@test -n "$(m)" || (echo 'usage: make autogenerate m="message"'; exit 1)
	uv run alembic revision --autogenerate -m "$(m)"

test:
	uv run pytest -v tests/$(p)/

cov:
	uv run pytest --cov --cov-report= $(p)
	uv run coverage report $(if $(f),--include="*$(f)",)

cov-html:
	uv run pytest --cov --cov-report=html $(p)
	@echo "open htmlcov/index.html"