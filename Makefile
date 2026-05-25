.PHONY: setup test lint format clean graph joern-up joern-down joern-logs joern-status joern-test verify extract compare

# Use uv for environment management if available, fallback to standard python
PYTHON = uv run python
PYTEST = uv run pytest
NEUROAST = $(PYTHON) -m neuroast.cli

setup:
	uv sync --group dev

# ── Phase 2: Joern CPG Server (Docker) ───────────────────────────────────────

## Start Joern server in the background. Joern takes ~60-90s to become healthy.
joern-up:
	docker compose up -d joern
	@echo "Joern starting — check health with: make joern-status"

## Stop Joern server (keeps the CPG cache volume).
joern-down:
	docker compose down

## Tail Joern server logs.
joern-logs:
	docker compose logs -f joern

## Show Joern container health and port binding.
joern-status:
	docker compose ps
	@echo ""
	@curl -sf http://localhost:8080/ > /dev/null && echo "✅  Joern HTTP server is UP (http://localhost:8080)" || echo "⏳  Joern is still starting (or not running). Try: make joern-up"

## Send a test CPGQL query to confirm Joern is accepting requests.
joern-test:
	@curl -s -X POST http://localhost:8080/query-sync \
		-H 'Content-Type: application/json' \
		-d '{"query": "1 + 1"}' | python3 -m json.tool

test:
	$(PYTEST) tests/ -v

lint:
	uv run ruff check .

format:
	uv run ruff format .

clean:
	rm -rf .pytest_cache
	rm -rf __pycache__
	rm -rf src/neuroast/__pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} +

# ── NeuroAST CLI shortcuts ────────────────────────────────────────────────────

## Translate C → Java with verification.  Usage: make verify SRC=path/to/file.c
verify:
	$(NEUROAST) verify $(SRC)

## Extract structural fingerprint.  Usage: make extract SRC=path/to/file.c LANG=c
extract:
	$(NEUROAST) extract $(SRC) -l $(or $(LANG),c)

## Compare C vs Java structures.  Usage: make compare SRC=file.c TGT=file.java
compare:
	$(NEUROAST) compare $(SRC) $(TGT)

graph:
	graphify . --update
