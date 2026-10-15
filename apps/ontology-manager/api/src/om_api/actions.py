"""Write-back through ontology actions (the only writes): POST /api/actions/{name}."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from t1d_ontology import actions as ontology_actions

from om_api.db import client

router = APIRouter(tags=["actions"])


def apply(name: str, params: dict) -> dict:
    c = client()
    result = ontology_actions.apply(c.ontology, c.cfg, name, params)
    obj = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in result["object"].items()}
    return result | {"object": obj}


@router.post("/actions/{name}")
def apply_action(name: str, params: Annotated[dict, Body()]) -> dict:
    try:
        return apply(name, params)
    except ontology_actions.ActionError as e:
        raise HTTPException(400, str(e)) from None
