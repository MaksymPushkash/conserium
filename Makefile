up:
	docker compose up

down:
	docker compose down
	
build:
	docker compose up --build

upgrade:
	docker exec -it cortex alembic upgrade head

downgrade:
	docker exec -it cortex alembic downgrade -1

migrate:
	docker exec -it cortex alembic revision --autogenerate -m "$(msg)"

logs:
	docker compose logs -f cortex
	
lint:
	uv run ruff check .

typecheck:
	uv run mypy .