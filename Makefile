.PHONY: install dev test test-backend test-frontend lint build clean

PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

install:
	$(PYTHON) -m pip install -e ".[test]"
	npm --prefix frontend install

dev:
	$(PYTHON) -m uvicorn app.main:create_app --factory --app-dir backend --reload --host 0.0.0.0 --port 8000

test: test-backend test-frontend

test-backend:
	$(PYTHON) -m pytest -q

test-frontend:
	npm --prefix frontend test -- --run

lint:
	npm --prefix frontend exec vue-tsc -- -b

build:
	npm --prefix frontend run build

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage frontend/dist
