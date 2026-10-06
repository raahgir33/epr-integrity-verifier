.PHONY: api-install api-dev api-test api-lint web-install web-dev web-build web-check

api-install:
	cd api && uv sync

api-dev:
	cd api && uv run uvicorn app.main:app --reload --port 8080

api-test:
	cd api && uv run pytest -q

api-lint:
	cd api && uv run ruff check . && uv run ruff format --check .

web-install:
	cd web && npm install

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm run build

web-check:
	cd web && npm run lint && npx tsc --noEmit
