"""Persistent object overrides and audit history; source Parquet files are never written.

SQLite stores individual field edits. DuckDB views project them over the exported base
so object browsing, SQL, profiles and agent tools all see the same effective values.
"""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from threading import RLock

from t1d_ontology.model import Ontology

EDIT_LOCK = RLock()
SQL_TYPES = {
    "string": "VARCHAR",
    "integer": "BIGINT",
    "double": "DOUBLE",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
}


@contextmanager
def connect(cfg):
    path = cfg.layers.writeback / "manager.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS overrides (
            object_type TEXT NOT NULL, primary_key TEXT NOT NULL, property TEXT NOT NULL,
            value TEXT NOT NULL, PRIMARY KEY (object_type, primary_key, property)
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            kind TEXT NOT NULL, object_type TEXT NOT NULL, primary_key TEXT,
            before_json TEXT NOT NULL, after_json TEXT NOT NULL
        );
    """)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def normalized(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def typed(value, kind):
    if value is None:
        return None
    if kind == "string" and isinstance(value, str):
        return value
    if kind == "boolean" and type(value) is bool:
        return value
    if kind == "integer" and type(value) is int and -(2**63) <= value < 2**63:
        return value
    if kind == "double" and type(value) in (float, int) and math.isfinite(value):
        return float(value)
    if kind == "date" and isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    if kind == "timestamp" and isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                raise ValueError("Use a timezone-free UTC timestamp matching the backing schema")
            return parsed.isoformat()
        except ValueError:
            pass
    raise ValueError(f"Expected {kind}; received {value!r}")


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def refresh_views(con, ont: Ontology, cfg, only: str | None = None):
    with connect(cfg) as store:
        for ot in ont.object_types.values():
            if only and ot.name != only:
                continue
            rows = store.execute("SELECT * FROM overrides WHERE object_type=?", (ot.name,)).fetchall()
            expressions = []
            for prop in ot.properties.values():
                matches = [r for r in rows if r["property"] == prop.name]
                if not matches:
                    continue
                cases = []
                for row in matches:
                    value = json.loads(row["value"])
                    literal = "NULL" if value is None else quote(value)
                    pk_type = SQL_TYPES[ot.properties[ot.primary_key].type]
                    cases.append(
                        f"WHEN {identifier(ot.primary_key)} = CAST({quote(row['primary_key'])} AS {pk_type}) "
                        f"THEN CAST({literal} AS {SQL_TYPES[prop.type]})"
                    )
                expressions.append(
                    f"CASE {' '.join(cases)} ELSE {identifier(prop.name)} END AS {identifier(prop.name)}"
                )
            replace = f" REPLACE ({', '.join(expressions)})" if expressions else ""
            con.execute(
                f"CREATE OR REPLACE VIEW {identifier(ot.name)} AS SELECT *{replace} "
                f"FROM read_parquet({quote(ot.path(cfg.layers.root))})"
            )


def audit(store, kind, object_type, pk, before, after):
    store.execute(
        "INSERT INTO history(kind,object_type,primary_key,before_json,after_json) VALUES (?,?,?,?,?)",
        (kind, object_type, pk, json.dumps(before, default=normalized), json.dumps(after, default=normalized)),
    )


def edit_record(client, type_name, pk, changes, expected):
    ot = client.ontology.object_types[type_name]
    if not isinstance(changes, dict) or not changes:
        raise ValueError("Supply at least one changed property")
    protected = {ot.primary_key} | {
        link.foreign_key for link in client.ontology.links_of(type_name) if link.many == type_name
    }
    for name in changes:
        if name not in ot.properties:
            raise ValueError(f"Unknown property: {name}")
        if name in protected:
            raise ValueError(f"{name} is a key; key edits require a schema migration")
    values = {k: typed(v, ot.properties[k].type) for k, v in changes.items()}
    with EDIT_LOCK:
        current = client.get(type_name, pk)
        if current is None:
            raise KeyError("Object not found")
        before = {k: normalized(current[k]) for k in values}
        if expected != before:
            raise RuntimeError("This object changed since it was opened. Reload before saving.")
        with connect(client.cfg) as store:
            for name, value in values.items():
                store.execute(
                    "INSERT OR REPLACE INTO overrides VALUES (?,?,?,?)", (type_name, str(pk), name, json.dumps(value))
                )
            audit(store, "object.edit", type_name, str(pk), before, values)
        refresh_views(client.con, client.ontology, client.cfg, type_name)
    return client.get(type_name, pk)


def reset_record(client, type_name, pk, expected):
    with EDIT_LOCK:
        current = client.get(type_name, pk)
        if current is None:
            raise KeyError("Object not found")
        with connect(client.cfg) as store:
            rows = store.execute(
                "SELECT property FROM overrides WHERE object_type=? AND primary_key=?", (type_name, str(pk))
            ).fetchall()
            before = {r["property"]: normalized(current[r["property"]]) for r in rows}
            if expected != before:
                raise RuntimeError("This object changed since it was opened. Reload before restoring.")
            ot = client.ontology.object_types[type_name]
            base = client.con.execute(
                f"SELECT * FROM read_parquet({quote(ot.path(client.cfg.layers.root))}) "
                f"WHERE {identifier(ot.primary_key)} = ?",
                [pk],
            ).pl()
            after = {k: normalized(base.row(0, named=True)[k]) for k in before}
            store.execute("DELETE FROM overrides WHERE object_type=? AND primary_key=?", (type_name, str(pk)))
            audit(store, "object.restore", type_name, str(pk), before, after)
        refresh_views(client.con, client.ontology, client.cfg, type_name)
    return client.get(type_name, pk)
