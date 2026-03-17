.DEFAULT_GOAL := help

.PHONY: help test lint check

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  test       Run tests"
	@echo "  lint       Run linting"
	@echo "  check      Run linting and tests"

test:
	uv sync --group dev --frozen
	uv run pytest

lint:
	uv sync --group dev --frozen
	uv run ruff check src --fix
	uv run ruff format src
	uv run mypy
	uv run pydoclint src
	uv run pylint src

check:
	make lint
	make test
