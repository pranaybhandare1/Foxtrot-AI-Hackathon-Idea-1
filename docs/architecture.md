# Architecture

## Goals

1. **Trustworthy data first.** Every number in the UI traces back to a CSV line and passes explicit checks.
2. **An ontology as the contract.** Analysis, the API and the UI speak in objects and links, not raw tables.
3. **Local and private.** Health data stays on the machine, with no cloud services involved.
4. **Easy to extend.** New sources (Oura, Apple Health) and a later decision-support layer slot in without rewrites.

## Packages (uv workspace)

```
          ┌──────────────┐
          │  t1d-core    │  settings: repo paths, config, layer layout
          └──────┬───────┘
                 │
          ┌──────▼───────┐
          │ t1d-ontology │  ontology.yaml → model · validation · publish · client SDK
          └──┬────────┬──┘
             │        │
 ┌───────────▼──┐  ┌──▼──────────┐
 │t1d-pipelines │  │  t1d-api    │  FastAPI, read-only, serves app/web/dist
 │ sources, QC, │  └──────▲──────┘
 │ `t1d` CLI    │         │ /api (JSON)
 └──────────────┘  ┌──────┴──────┐
                   │   app/web   │  React + TS + ECharts (Pranay360)
                   └─────────────┘
```

Dependencies point one way: the pipelines and the API depend on the ontology, and nothing depends on the API.
The web app talks only to `/api`.

## Medallion layers

| Layer | Contract | Format |
|---|---|---|
| landing | Exact bytes of each export, checksum-verified, read-only, one folder per batch | CSV |
| raw | One row per source row, strings only, original column names, lineage, no PII | Parquet |
| transformed | Typed, classified (`event_type`), UTC-corrected, deduped across batches, full history | Parquet |
| clean | Scoped (Instinct era), one table per ontology type, stable keys, analysis features | Parquet |
| warehouse | DuckDB views over every layer + `ontology."<Type>"` views | DuckDB |

Rebuilding is deterministic and fast (~2 s), so there is no incremental machinery. `make pipeline` always rebuilds raw → clean from landing.

## The ontology

`ontology/ontology.yaml` declares object types (primary key, typed properties, backing dataset), dense
datasets (`Glucose5Min`) and link types (declared by a foreign-key property). The build validates the data
against it and **fails** on any drift. It then publishes DuckDB views and a generated catalog
(`data/reports/ontology_catalog.md`) with an ER diagram.

Each type also carries Ontology-Manager metadata: a `display` group, icon and colour, and its `sources`.

**Write-back and actions.** Like Foundry, the application layer writes to the ontology only through typed
actions (`action_types` in the YAML: `create_experiment`, `update_experiment`, `add_day_note`).
`t1d_ontology.actions` validates the parameters and rewrites the backing Parquet atomically under
`data/writeback/`, which the pipeline never rebuilds (see [ADR 0006](decisions/0006-writeback-actions.md)).

`t1d_ontology.client.OntologyClient` gives an OSDK-style interface: `objects("Meal").where(...).search_around("meal_bolus")`.
The API's generic explorer endpoints use the same metadata, so new types appear in the UI without code changes.

## Time model (the hard part)

Pump timestamps are a hand-set wall clock (DST, travel, typos). UTC is reconstructed from the logged clock
changes, anchored on the clock's known offset at export time. Pump events are ordered by their true
sequence. Sensor readings are stamped *at receipt*, so they are assigned to clock segments by receipt order.
True local time uses the home timezone's DST rules at home, and the pump's own offset while travelling.
Quality check T5 verifies the result independently: pump alert values match CGM values in every clock segment.
Details are in [data-sources/carelink.md](data-sources/carelink.md) and [ADR 0004](decisions/0004-pump-clock-reconstruction.md).

## API

JSON under `/api`, one router per report area (`routes/`). Everything is read-only except
`POST /api/actions/{name}`. `insights.py` is the insights engine: declarative condition-vs-baseline
comparisons (night, day, meal or workout units) with n, Welch p and effect size, plus the experiment metric catalog. A single filter model
(`filters.py`: date range, day type, exclude travel, valid days) turns into a `WITH days AS (...)`
CTE that every query joins to, so all reports filter identically. Each request gets its own DuckDB cursor
over views that read Parquet at query time, so a pipeline rebuild needs no API restart.

## Web app

- Information architecture: Today → three pillars (Glucose, Sleep & recovery, Insights & experiments) →
  clinic report → platform (Ontology Manager, data health). Pillars use a second-level tab strip
  (`components/PillarTabs.tsx`); pre-restructure URLs redirect and keep their query string.
- `state/filters.tsx`: global filters in the URL (shareable, back/forward-friendly).
- `api/client.ts`: TanStack Query hooks keyed by filters; `api/types.ts`: response types.
- `components/`: glass UI primitives, the ECharts wrapper (theme-aware), a virtualized sortable table,
  and glucose visuals (range bar, mini traces).
- `styles/tokens.css`: every color, radius, blur and motion token, dark and light.
  Clinical range colors follow the AGP convention.

## Extending to Oura / Apple Health

New sources are new `pipelines/.../sources/<name>/` packages with the same layer contracts. Their objects
link to `Day` (`date_local`) for day-level questions such as sleep vs. next-day insulin need, and join to
`Glucose5Min` on `bin_start_utc` for intraday questions such as workouts vs. lows.
