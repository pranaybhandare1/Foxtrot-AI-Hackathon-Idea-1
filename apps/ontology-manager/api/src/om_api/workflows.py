"""Workflow ideas (apps/ontology-manager/workflows.yaml), validated against the ontology."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter

from om_api.db import client

router = APIRouter(tags=["workflows"])
WORKFLOWS_FILE = Path(__file__).resolve().parents[3] / "workflows.yaml"


def _text(v) -> str:
    if isinstance(v, dict):
        return "; ".join(f"{k}: {val}" for k, val in v.items())
    return str(v)


@router.get("/workflows")
def workflows() -> dict:
    ont = client().ontology
    items = (yaml.safe_load(WORKFLOWS_FILE.read_text()) or {}).get("workflows", []) if WORKFLOWS_FILE.exists() else []
    for w in items:
        # YAML turns "Optional: do x" into a mapping; keep every list item / text field a plain string for the UI
        for key in ("reads", "writes", "visuals", "steps"):
            w[key] = [_text(v) for v in w.get(key) or []]
        for key in ("title", "trigger", "agent", "evidence"):
            if key in w and w[key] is not None:
                w[key] = _text(w[key])
        # flag references that don't exist in the ontology (typos, renamed types)
        w["unknown"] = [r for r in w.get("reads", []) if r not in ont.object_types] + [
            a for a in w.get("writes", []) if a not in ont.action_types
        ]
    return {"file": str(WORKFLOWS_FILE.relative_to(WORKFLOWS_FILE.parents[2])), "workflows": items}
