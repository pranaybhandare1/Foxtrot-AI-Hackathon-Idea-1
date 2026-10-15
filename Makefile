.PHONY: help setup validate test quickstart sql om om-dev om-api
UV := $(shell command -v uv 2>/dev/null)
WEB := apps/ontology-manager/web
# Node comes from the nodejs-wheel dev dependency (no system Node needed)
NPM := PATH="$(CURDIR)/.venv/bin:$$PATH" npm

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

om: ## Build the Ontology Manager UI and serve it at http://127.0.0.1:8770
	cd $(WEB) && $(NPM) install --no-audit --no-fund --silent && $(NPM) run build
	$(UV) run ontology-manager

om-api: ## Run only the Ontology Manager API (auto-reload) on :8770
	OM_RELOAD=1 $(UV) run ontology-manager

om-dev: ## UI dev server with hot reload on :5174 (run `make om-api` in another terminal)
	cd $(WEB) && $(NPM) install --no-audit --no-fund --silent && $(NPM) run dev
