up:
	docker compose up

down:
	docker compose down
	
build:
	docker compose up --build

upgrade:
	alembic upgrade head

downgrade:
	alembic downgrade -1

migrate:
	alembic revision --autogenerate -m "$(msg)"

logs:
	docker compose logs -f app
	
lint:
	uv run ruff check .

typecheck:
	uv run mypy .
