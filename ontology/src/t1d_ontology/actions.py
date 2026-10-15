"""Ontology actions: the only way the application layer writes to the ontology (Foundry "actions").

Each action type in ontology.yaml declares typed parameters and the object type it creates or
modifies. `apply` validates the parameters against that spec, then rewrites the backing Parquet
file atomically (write to a temp file, then rename). Write-back tables live in `data/writeback/`,
which the pipeline never rebuilds, so user-authored objects survive `make pipeline`.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
from t1d_core.settings import Config

from t1d_ontology.model import ActionType, ObjectType, Ontology

POLARS = {
    "string": pl.Utf8,
    "integer": pl.Int64,
    "double": pl.Float64,
    "boolean": pl.Boolean,
    "date": pl.Date,
    "timestamp": pl.Datetime("us"),
}


class ActionError(ValueError):
    """Invalid parameters, or a modify action that targets a missing object."""


def _writeback_types(ont: Ontology) -> list[ObjectType]:
    return [ot for ot in ont.object_types.values() if ot.backing_dataset.startswith("writeback/")]


def schema(ot: ObjectType) -> dict[str, pl.DataType]:
    return {p.name: POLARS[p.type] for p in ot.properties.values()}


def ensure_tables(ont: Ontology, cfg: Config) -> None:
    """Create empty, correctly typed tables for write-back types that have no data yet."""
    for ot in _writeback_types(ont):
        path = ot.path(cfg.layers.root)
        if not path.exists():
            _write(pl.DataFrame(schema=schema(ot)), path)


def _write(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.write_parquet(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _coerce(name: str, kind: str, value):
    if value is None or value == "":
        return None
    try:
        if kind == "string":
            return str(value).strip()
        if kind == "integer":
            return int(value)
        if kind == "double":
            return float(value)
        if kind == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("1", "true", "yes")
        if kind == "date":
            return value if isinstance(value, date) else date.fromisoformat(str(value))
        if kind == "timestamp":
            return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as e:
        raise ActionError(f"{name}: expected {kind}, got {value!r}") from e
    raise ActionError(f"{name}: unsupported type {kind}")


def validate_params(at: ActionType, params: dict) -> dict:
    unknown = params.keys() - at.parameters.keys()
    if unknown:
        raise ActionError(f"unknown parameters: {sorted(unknown)}")
    out = {}
    for p in at.parameters.values():
        v = _coerce(p.name, p.type, params.get(p.name))
        if v is None and p.required:
            raise ActionError(f"{p.name} is required")
        if v is not None and p.enum and v not in p.enum:
            raise ActionError(f"{p.name} must be one of {list(p.enum)}")
        if v is not None:
            out[p.name] = v
    if "start_date" in out and "end_date" in out and out["end_date"] < out["start_date"]:
        raise ActionError("end_date is before start_date")
    return out


def apply(ont: Ontology, cfg: Config, action: str, params: dict) -> dict:
    """Run an action and return the created or modified object."""
    at = ont.action_types.get(action)
    if at is None:
        raise ActionError(f"unknown action {action}")
    values = validate_params(at, params)
    ot = ont.object_types[at.object_type]
    path = ot.path(cfg.layers.root)
    ensure_tables(ont, cfg)
    df = pl.read_parquet(path)
    now = datetime.now(UTC).replace(tzinfo=None)
    pk = ot.primary_key

    if at.kind == "create":
        row = {c: None for c in ot.properties} | values
        row[pk] = row.get(pk) or uuid.uuid4().hex[:12]
        if "status" in ot.properties and row.get("status") is None:
            row["status"] = "active"
        for stamp in ("created_at", "updated_at"):
            if stamp in ot.properties:
                row[stamp] = now
        df = pl.concat([df, pl.DataFrame([row], schema=schema(ot))])
    else:
        key = values.pop(pk, None)
        if key is None or key not in df[pk].to_list():
            raise ActionError(f"{ot.name} {key!r} not found")
        if "updated_at" in ot.properties:
            values["updated_at"] = now
        df = df.with_columns(
            pl.when(pl.col(pk) == key).then(pl.lit(v, dtype=schema(ot)[c])).otherwise(pl.col(c)).alias(c)
            for c, v in values.items()
        )
        row = df.filter(pl.col(pk) == key).row(0, named=True)
    _write(df, path)
    return {"action": action, "object_type": ot.name, "primary_key": row[pk], "object": row}
