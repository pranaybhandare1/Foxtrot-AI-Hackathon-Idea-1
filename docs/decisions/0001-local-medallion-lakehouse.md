# 0001: Local medallion lakehouse on Parquet + DuckDB

**Status:** accepted · 2026-09-26

## Context
The data is personal health data, small (≈100k rows per 8 months per source), and must be trustworthy
and traceable to its source rows.

## Decision
Four layers (landing → raw → transformed → clean) stored as Parquet under `data/`, with DuckDB views for
querying. Landing is immutable and checksum-verified. Every layer is rebuilt from landing on each run.

## Consequences
- No servers and no cloud: nothing leaves the machine.
- Full rebuilds take about 2 s, so there's no incremental/merge logic to get wrong.
- Overlapping future exports are handled by dedupe in transformed, where the latest batch wins.
- Revisit if the data grows by ~100×.
