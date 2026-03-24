.PHONY: lint format test ci

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .

test:
	pytest

ci: lint test
