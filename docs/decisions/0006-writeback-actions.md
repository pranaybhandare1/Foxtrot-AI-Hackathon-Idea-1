# 0006: Write-back through ontology actions

**Status:** accepted (2026-10-14)

## Context

The platform is moving from reports to an application layer: start an experiment from an insight,
mark it complete, add context to a day. These are user-authored objects. They must survive pipeline
rebuilds, they must be queryable like everything else, and their writes must be validated.

## Decision

- User-authored types (`Experiment`, `DayNote`) are ordinary ontology object types backed by
  `data/writeback/<name>.parquet`, marked `optional` so an empty table validates.
- Writes happen only through **action types** declared in `ontology.yaml`, with typed, enum-checked,
  required-aware parameters. `t1d_ontology.actions.apply` validates them and rewrites the file atomically
  (temp file + rename). The API exposes a single write route, `POST /api/actions/{name}`.
- `make pipeline` and `make clean-data` never touch `data/writeback/`. Missing tables are created empty
  and typed on first use.
- The UI generates action forms from the action spec, like Foundry action forms.

## Consequences

- One write path to audit. New write-back features are YAML plus, at most, a metric definition.
- Parquet rewrite-on-write is fine for a single user and hundreds of rows. If multi-user or high-volume
  writes ever arrive, swap the storage behind `actions.apply` (e.g. DuckDB tables) without changing callers.
- Experiments are evaluated against the 28 days before they start. Results lag until a fresh CareLink export is loaded.
