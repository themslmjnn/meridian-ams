.PHONY: format migrate migration autogenerate

format:
	uv run ruff format .

migrate:
	uv run alembic upgrade head

migration:
	@test -n "$(m)" || (echo 'usage: make migration m="message"'; exit 1)
	uv run alembic revision -m "$(m)"

autogenerate:
	@test -n "$(m)" || (echo 'usage: make autogenerate m="message"'; exit 1)
	uv run alembic revision --autogenerate -m "$(m)"