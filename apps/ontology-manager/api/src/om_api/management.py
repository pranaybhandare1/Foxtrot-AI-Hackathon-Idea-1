"""Local ontology management: metadata, isolated object overrides, audit history, lineage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from t1d_core.settings import ONTOLOGY_FILE
from t1d_ontology.edits import EDIT_LOCK, audit, connect, edit_record, identifier, normalized, quote, reset_record
from t1d_ontology.model import load

from om_api.db import client, records

router = APIRouter(prefix="/management", tags=["management"])


def revision(path=ONTOLOGY_FILE):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_type(name):
    ot = client().ontology.object_types.get(name)
    if ot is None:
        raise HTTPException(404, "Unknown object type")
    return ot


@router.get("/state")
def state():
    with connect(client().cfg) as store:
        edits = store.execute("SELECT count(*) FROM overrides").fetchone()[0]
        count = store.execute("SELECT count(*) FROM history").fetchone()[0]
    return {
        "revision": revision(),
        "overrides": edits,
        "changes": count,
        "schema_file": "ontology/ontology.yaml",
        "edit_store": "data/writeback/manager.sqlite",
    }


def save_metadata(type_name, body, prop=None, path=ONTOLOGY_FILE):
    ot = checked_type(type_name)
    allowed = {"description", "display_name"} if prop else {"description", "group", "color", "title"}
    changes = body.get("changes")
    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
        raise HTTPException(400, f"Allowed fields: {', '.join(sorted(allowed))}")
    if any(not isinstance(v, str) for v in changes.values()):
        raise HTTPException(400, "Metadata values must be strings")
    if any(len(v) > 10000 for v in changes.values()):
        raise HTTPException(400, "Metadata values must be under 10,000 characters")
    if prop and prop not in ot.properties:
        raise HTTPException(404, "Unknown property")
    if "color" in changes and not re.fullmatch(r"#[0-9a-fA-F]{6}", changes["color"]):
        raise HTTPException(400, "Color must be a six-digit hex color")
    if "group" in changes and changes["group"] not in client().ontology.groups:
        raise HTTPException(400, "Unknown group")
    if "title" in changes and changes["title"] not in ot.properties:
        raise HTTPException(400, "Title must name an existing property")
    with EDIT_LOCK:
        if body.get("revision") != revision(path):
            raise HTTPException(409, "The ontology changed. Reload the editor before saving.")
        original = path.read_bytes()
        spec = yaml.safe_load(original)
        section = "datasets" if ot.is_dataset else "object_types"
        target = spec[section][type_name]
        before = {}
        for name, value in changes.items():
            dest = (
                target["properties"][prop]
                if prop
                else target.setdefault("display", {})
                if name in {"group", "color"}
                else target
            )
            before[name] = dest.get(name, "")
            dest[name] = value
        tmp = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=path.parent, suffix=".yaml", delete=False) as f:
                yaml.safe_dump(spec, f, sort_keys=False, allow_unicode=True)
                tmp = Path(f.name)
            updated = load(tmp)
            with connect(client().cfg) as store:
                audit(store, "property.metadata" if prop else "type.metadata", type_name, prop, before, changes)
                os.replace(tmp, path)
            client().ontology = updated
        except Exception:
            # If persistence fails after replacement, keep disk and in-memory schema consistent.
            if path.read_bytes() != original:
                path.write_bytes(original)
            raise
        finally:
            if tmp and tmp.exists():
                tmp.unlink()
    return {"revision": revision(path), "saved": changes}


@router.post("/types/{type_name}")
def update_type(type_name: str, body: dict):
    return save_metadata(type_name, body)


@router.post("/types/{type_name}/properties/{property_name}")
def update_property(type_name: str, property_name: str, body: dict):
    return save_metadata(type_name, body, property_name)


@router.get("/objects/{type_name}/{pk}")
def object_edit_context(type_name: str, pk: str):
    ot = checked_type(type_name)
    c = client()
    current = c.get(type_name, pk)
    if current is None:
        raise HTTPException(404, "Object not found")
    base = c.con.execute(
        f"SELECT * FROM read_parquet({quote(ot.path(c.cfg.layers.root))}) WHERE {identifier(ot.primary_key)} = ?", [pk]
    ).pl()
    with connect(c.cfg) as store:
        edits = store.execute(
            "SELECT property,value FROM overrides WHERE object_type=? AND primary_key=?", (type_name, pk)
        ).fetchall()
    protected = {ot.primary_key} | {
        link.foreign_key for link in c.ontology.links_of(type_name) if link.many == type_name
    }
    return {
        "object": {k: normalized(v) for k, v in current.items()},
        "base": records(base)[0],
        "overrides": {r["property"]: json.loads(r["value"]) for r in edits},
        "protected": sorted(protected),
    }


def mutate_record(type_name, pk, body, reset=False):
    checked_type(type_name)
    try:
        if reset:
            result = reset_record(client(), type_name, pk, body.get("expected"))
        else:
            result = edit_record(client(), type_name, pk, body.get("changes"), body.get("expected"))
        return {"object": {k: normalized(v) for k, v in result.items()}}
    except KeyError as e:
        raise HTTPException(404, str(e)) from None
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e)) from None
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from None


@router.post("/objects/{type_name}/{pk}")
def update_record(type_name: str, pk: str, body: dict):
    return mutate_record(type_name, pk, body)


@router.post("/objects/{type_name}/{pk}/restore")
def restore_record(type_name: str, pk: str, body: dict):
    return mutate_record(type_name, pk, body, reset=True)


@router.get("/history")
def history():
    with connect(client().cfg) as store:
        entries = store.execute("SELECT * FROM history ORDER BY id DESC LIMIT 200").fetchall()
    return {
        "entries": [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "kind": r["kind"],
                "object_type": r["object_type"],
                "primary_key": r["primary_key"],
                "before": json.loads(r["before_json"]),
                "after": json.loads(r["after_json"]),
            }
            for r in entries
        ]
    }


@router.get("/lineage")
def lineage():
    c = client()
    nodes, edges = {}, []

    def node(id, label, layer, **extra):
        nodes[id] = {"id": id, "label": label, "layer": layer, **extra}

    for source in ("carelink", "oura"):
        node(source, "CareLink exports" if source == "carelink" else "Oura API", "source", available=False)
        previous = source
        for layer in ("raw", "transformed"):
            id = f"{layer}/{source}"
            node(id, f"{source} / {layer}", layer, available=(c.cfg.layers.root / id).exists())
            edges.append({"source": previous, "target": id, "kind": "pipeline"})
            previous = id
    node("actions", "User actions", "source", available=True)
    node("overrides", "Object value overrides", "edits", available=True, path="data/writeback/manager.sqlite")
    for ot in c.ontology.object_types.values():
        dataset = ot.backing_dataset
        node(
            dataset,
            dataset,
            "writeback" if dataset.startswith("writeback/") else "clean",
            available=ot.path(c.cfg.layers.root).exists(),
            path=f"data/{dataset}.parquet",
            object_type=ot.name,
        )
        node(f"object/{ot.name}", ot.name, "ontology", available=True, object_type=ot.name)
        for source in ot.sources:
            edges.append(
                {
                    "source": "actions" if source == "writeback" else f"transformed/{source}",
                    "target": dataset,
                    "kind": "pipeline",
                }
            )
        edges.append({"source": dataset, "target": f"object/{ot.name}", "kind": "mapping"})
        edges.append({"source": "overrides", "target": f"object/{ot.name}", "kind": "override"})
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "basis": "Declared source and backing-dataset mappings; upstream layers are not shipped with this repository.",
    }
