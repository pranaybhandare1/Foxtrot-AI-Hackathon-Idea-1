.PHONY: help setup validate test quickstart sql
UV := $(shell command -v uv 2>/dev/null)

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Create the virtualenv and install the packages (needs uv: https://docs.astral.sh/uv/)
	$(UV) sync

validate: ## Check the data against ontology.yaml (types, keys, links)
	$(UV) run python -c "from t1d_core.settings import load_config; from t1d_ontology.model import load; from t1d_ontology.validation import validate; from t1d_ontology.actions import ensure_tables; o, c = load(), load_config(); ensure_tables(o, c); r = validate(o, c); print('\n'.join(r['errors']) or 'ontology valid'); raise SystemExit(bool(r['errors']))"

test: ## Run the tests that don't need the original exports
	$(UV) run pytest

quickstart: ## Run the example queries
	$(UV) run python examples/quickstart.py

sql: ## Open the portable DuckDB file (needs the duckdb CLI)
	duckdb data/ontology.duckdb
