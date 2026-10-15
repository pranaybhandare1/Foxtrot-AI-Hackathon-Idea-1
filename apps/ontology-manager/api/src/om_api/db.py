"""One in-process DuckDB with a view per ontology object type (via the ontology SDK), a cursor per request."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

import duckdb
import polars as pl
from t1d_ontology.client import OntologyClient


@lru_cache(maxsize=1)
def client() -> OntologyClient:
    return OntologyClient()


def cursor() -> Iterator[duckdb.DuckDBPyConnection]:
    """FastAPI dependency: a fresh cursor per request (DuckDB cursors are thread-safe to use this way)."""
    cur = client().con.cursor()
    try:
        yield cur
    finally:
        cur.close()


def query(cur: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> pl.DataFrame:
    return cur.execute(sql, params or []).pl()


def records(df: pl.DataFrame) -> list[dict]:
    """JSON-safe rows: NaN/inf -> null; HUGEINT/DECIMAL -> plain numbers; temporal -> ISO strings by FastAPI."""

    def plain(t: pl.DataType) -> pl.DataType:
        return pl.Int64 if t == pl.Int128 or (isinstance(t, pl.Decimal) and t.scale == 0) else pl.Float64

    df = df.with_columns(
        [pl.col(c).cast(plain(t)) for c, t in df.schema.items() if t == pl.Int128 or isinstance(t, pl.Decimal)]
    )
    floats = [c for c, t in df.schema.items() if t.is_float()]
    if floats:
        df = df.with_columns([pl.when(pl.col(c).is_finite()).then(pl.col(c)).otherwise(None).alias(c) for c in floats])
    nested = [c for c, t in df.schema.items() if t.is_nested()]
    if nested:
        df = df.with_columns([pl.col(c).cast(pl.Utf8, strict=False) for c in nested])
    return df.to_dicts()


SQL_TYPES = {
    "string": "VARCHAR", "integer": "BIGINT", "double": "DOUBLE",
    "boolean": "BOOLEAN", "date": "DATE", "timestamp": "TIMESTAMP",
}  # fmt: skip
