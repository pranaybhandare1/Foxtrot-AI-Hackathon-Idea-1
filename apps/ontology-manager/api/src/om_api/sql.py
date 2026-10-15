"""Read-only SQL over the ontology views, for exploration and quick visuals.

Only SELECT statements run (checked by DuckDB's own parser), one statement per request, capped rows.
"""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Body, Depends, HTTPException

from om_api.db import cursor, query, records

router = APIRouter(tags=["sql"])
MAX_ROWS = 10_000


def run_select(cur: duckdb.DuckDBPyConnection, sql: str, limit: int = MAX_ROWS) -> dict:
    try:
        statements = cur.extract_statements(sql)
    except duckdb.Error as e:
        raise ValueError(str(e).splitlines()[0]) from None
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise ValueError("only a single SELECT (or WITH … SELECT) statement is allowed")
    limit = max(1, min(int(limit), MAX_ROWS))
    try:
        df = query(cur, f"SELECT * FROM ({statements[0].query}) AS q LIMIT {limit + 1}")
    except duckdb.Error as e:
        raise ValueError(str(e).splitlines()[0]) from None
    truncated = df.height > limit
    df = df.head(limit)
    return {
        "columns": [{"name": c, "type": str(t)} for c, t in df.schema.items()],
        "rows": records(df),
        "truncated": truncated,
    }


@router.post("/sql")
def sql(body: dict = Body(...), cur=Depends(cursor)) -> dict:  # noqa: B008
    try:
        return run_select(cur, str(body.get("sql", "")), int(body.get("limit", MAX_ROWS)))
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
