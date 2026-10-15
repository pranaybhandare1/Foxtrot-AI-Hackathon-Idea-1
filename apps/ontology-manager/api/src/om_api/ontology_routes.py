"""Ontology metadata (everything the Ontology Manager renders) and per-type data profiles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from om_api.db import client, cursor, query, records

router = APIRouter(tags=["ontology"])

# Upstream lineage per source, shown on each object type's Datasources tab. The originals live in the
# private pipeline repo; this repo ships the clean layer only.
SOURCE_LINEAGE = {
    "carelink": ["landing/carelink (private)", "raw/carelink_events", "transformed/carelink_events"],
    "oura": ["landing/oura (private)", "raw/oura_documents", "transformed/oura_daily · oura_sleep · oura_workout"],
    "writeback": ["actions (Ontology Manager)"],
}


def object_type(name: str):
    ot = client().ontology.object_types.get(name)
    if ot is None:
        raise HTTPException(404, f"unknown object type {name}")
    return ot


@router.get("/ontology")
def ontology(cur=Depends(cursor)) -> dict:
    ont = client().ontology
    root = client().cfg.layers.root
    types = []
    for ot in ont.object_types.values():
        path = ot.path(root)
        types.append({
            "name": ot.name, "description": ot.description, "primary_key": ot.primary_key, "title": ot.title,
            "is_dataset": ot.is_dataset, "optional": ot.optional, "group": ot.group, "icon": ot.icon, "color": ot.color,
            "sources": list(ot.sources), "backing_dataset": ot.backing_dataset,
            "updated_at": path.stat().st_mtime if path.exists() else None,
            "lineage": [step for src in ot.sources for step in SOURCE_LINEAGE.get(src, [])],
            "count": cur.execute(f'SELECT count(*) FROM "{ot.name}"').fetchone()[0],
            "properties": [{"name": p.name, "type": p.type, "description": p.description, "display_name": p.display_name} for p in ot.properties.values()],
            "links": [
                {"name": lt.name, "many": lt.many, "one": lt.one, "foreign_key": lt.foreign_key,
                 "direction": "to_one" if lt.many == ot.name else "to_many",
                 "target": lt.one if lt.many == ot.name else lt.many}
                for lt in ont.links_of(ot.name)
            ],
            "actions": [a.name for a in ont.action_types.values() if a.object_type == ot.name],
        })  # fmt: skip
    return {
        "name": ont.name,
        "version": ont.version,
        "groups": [{"name": g.name, "display_name": g.display_name, "description": g.description} for g in ont.groups.values()],
        "object_types": types,
        "link_types": [
            {"name": lt.name, "many": lt.many, "one": lt.one, "foreign_key": lt.foreign_key, "required": lt.required}
            for lt in ont.link_types.values()
        ],
        "action_types": [
            {"name": a.name, "display_name": a.display_name, "description": a.description, "kind": a.kind,
             "object_type": a.object_type,
             "parameters": [{"name": p.name, "type": p.type, "required": p.required, "enum": list(p.enum)}
                            for p in a.parameters.values()]}
            for a in ont.action_types.values()
        ],
    }  # fmt: skip


@router.get("/objects/{type_name}/profile")
def profile(type_name: str, cur=Depends(cursor)) -> dict:
    """Per-property data profile: null %, distinct values, min / max / mean / quartiles, top values for categoricals."""
    ot = object_type(type_name)
    n = cur.execute(f'SELECT count(*) FROM "{ot.name}"').fetchone()[0]
    if n == 0:
        return {"count": 0, "properties": {}}
    summary = {r["column_name"]: r for r in records(query(cur, f'SUMMARIZE "{ot.name}"'))}
    out = {}
    for p in ot.properties.values():
        s = summary.get(p.name, {})
        null_pct = s.get("null_percentage")
        prof = {
            "null_pct": float(str(null_pct).rstrip("%")) / 100 if null_pct is not None else None,
            "distinct": s.get("approx_unique"),
            "min": s.get("min"), "max": s.get("max"),
            "mean": s.get("avg"), "std": s.get("std"),
            "q25": s.get("q25"), "q50": s.get("q50"), "q75": s.get("q75"),
        }  # fmt: skip
        if p.type in ("string", "boolean") and (s.get("approx_unique") or 0) <= 50:
            prof["top"] = records(
                query(
                    cur,
                    f'SELECT CAST("{p.name}" AS VARCHAR) AS value, count(*) AS n FROM "{ot.name}" '
                    f'WHERE "{p.name}" IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 6',
                )
            )
        out[p.name] = prof
    return {"count": n, "properties": out}
