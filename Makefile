# Makefile for NotebookLM MCP Server

.PHONY: help install test lint format typecheck check clean run

help: ## Show this help message
	@echo "NotebookLM MCP Server - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""

install: ## Install dependencies
	uv sync --prerelease=allow

install-browsers: ## Install Playwright browsers
	uv run playwright install chromium --with-deps

test: ## Run test suite with pytest
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest tests/ -v --cov=src --cov-report=term

lint: ## Run linter (ruff)
	uv run ruff check src

format: ## Format code with ruff
	uv run ruff format src

type-check: ## Run type checker (pyright)
	uv run pyright src

check: ## Run all checks (lint + typecheck)
	@echo "Running code quality checks..."
	@echo ""
	@echo "Ruff (linting):"
	@uv run ruff check src
	@echo ""
	@echo "Pyright (type checking):"
	@uv run pyright src
	@echo ""
	@echo "All checks passed!"

fix: ## Auto-fix linting issues
	uv run ruff check --fix src

fix-unsafe: ## Auto-fix linting issues (including unsafe fixes)
	uv run ruff check --fix --unsafe-fixes src

clean: ## Clean cache and build files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

start: ## Run the server (development mode)
	uv run notebooklm-mcp

all-checks:
	make lint
	make test
	make type-check
