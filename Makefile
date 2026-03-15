BACKEND_DIR := backend
PYTHON      := python3

.PHONY: lint format typecheck check test install

## Install all backend dependencies
install:
	pip install -r $(BACKEND_DIR)/requirements.txt

## Run ruff linter
lint:
	ruff check $(BACKEND_DIR)

## Run ruff formatter
format:
	ruff format $(BACKEND_DIR)

## Run mypy type checker
typecheck:
	mypy $(BACKEND_DIR)/app

## Run lint + format check + typecheck together
check: lint typecheck

## Run tests
test:
	cd $(BACKEND_DIR) && pytest
