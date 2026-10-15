# data/

`clean/` is the shared clean layer (one Parquet file per ontology object type), `ontology.duckdb` the same as DuckDB tables, `reports/` the generated catalog and quality report. Originals and intermediate layers are deliberately not shared. `writeback/` (created on first action) is git-ignored.
