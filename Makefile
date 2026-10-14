.PHONY: setup test lint typecheck reproduce reproduce-small tune serve web-dev deploy deploy-api deploy-web smoke clean-room

PY := uv run python

setup:
	uv sync --frozen
	cd web && npm ci

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy .

tune:
	$(PY) -m evaluation.harness tune

reproduce:
	$(PY) -m evaluation.harness reproduce

reproduce-small:
	$(PY) -m evaluation.harness reproduce --small --out .ci-results

serve:
	uv run uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload

web-dev:
	cd web && npm run dev

deploy: deploy-api deploy-web

deploy-api:
	./deploy/deploy-api.sh

deploy-web:
	./deploy/deploy-web.sh

smoke:
	$(PY) -m deploy.smoke

clean-room:
	./deploy/clean-room.sh
