PYTHON := python3

.PHONY: lint format typecheck check test install serve

## Install all backend dependencies
install:
	pip install -r requirements.txt

## Run ruff linter
lint:
	ruff check .

## Run ruff formatter
format:
	ruff format .

## Run mypy type checker
typecheck:
	mypy app

## Run lint + format check + typecheck together
check: lint typecheck

## Run tests
test:
	pytest

## Run the server
serve:
	uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload