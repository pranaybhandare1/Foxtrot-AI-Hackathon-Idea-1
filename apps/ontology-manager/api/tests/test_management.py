"""Real persistence and API checks over a temporary lake; never edit the personal dataset."""

import hashlib

import polars as pl
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from om_api import management
from t1d_core.settings import Config, Layers
from t1d_ontology.client import OntologyClient
from t1d_ontology.edits import edit_record, reset_record
from t1d_ontology.model import load


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for layer in ("raw", "transformed", "clean"):
        (tmp_path / layer).mkdir()
    for layer in ("raw", "transformed"):
        (tmp_path / layer / "sentinel.txt").write_text("unchanged upstream data")
    pl.DataFrame(
        {
            "id": ["a", "b"],
            "name": ["Alpha", "Beta"],
            "score": [10.0, 20.0],
            "parent": ["a", "a"],
            "active": [True, False],
            "count": [1, 2],
        }
    ).write_parquet(tmp_path / "clean" / "item.parquet")
    spec = {
        "ontology": "test",
        "version": 1,
        "groups": {"test": {"display_name": "Test"}},
        "object_types": {
            "Item": {
                "description": "Fixture",
                "backing_dataset": "clean/item",
                "primary_key": "id",
                "display": {"group": "test"},
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "score": {"type": "double"},
                    "parent": {"type": "string"},
                    "active": {"type": "boolean"},
                    "count": {"type": "integer"},
                },
            }
        },
        "link_types": {"parent": {"from": "Item.parent", "to": "Item"}},
    }
    path = tmp_path / "ontology.yaml"
    path.write_text(yaml.safe_dump(spec))
    cfg = Config(raw={}, layers=Layers(tmp_path))
    c = OntologyClient(cfg, load(path))
    monkeypatch.setattr(management, "client", lambda: c)
    app = FastAPI()
    app.include_router(management.router, prefix="/api")
    return c, path, TestClient(app)


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for layer in ("raw", "transformed", "clean")
        for p in (root / layer).rglob("*")
        if p.is_file()
    }


def test_overrides_persist_across_restart_and_do_not_modify_sources(workspace):
    c, path, api = workspace
    baseline = hashes(c.cfg.layers.root)
    r = api.post(
        "/api/management/objects/Item/a",
        json={"changes": {"score": 42.5, "name": None}, "expected": {"score": 10.0, "name": "Alpha"}},
    )
    assert r.status_code == 200, r.text
    assert c.sql("SELECT score,name FROM \"Item\" WHERE id='a'").row(0) == (42.5, None)
    fresh = OntologyClient(c.cfg, load(path))
    assert fresh.get("Item", "a")["score"] == 42.5
    assert fresh.get("Item", "a")["name"] is None
    assert hashes(c.cfg.layers.root) == baseline
    context = api.get("/api/management/objects/Item/a").json()
    assert context["base"]["score"] == 10.0 and context["overrides"]["score"] == 42.5
    assert (
        api.post("/api/management/objects/Item/a/restore", json={"expected": context["overrides"]}).status_code == 200
    )
    assert c.get("Item", "a")["score"] == 10.0
    assert OntologyClient(c.cfg, load(path)).get("Item", "a")["name"] == "Alpha"
    assert hashes(c.cfg.layers.root) == baseline
    history = api.get("/api/management/history").json()["entries"]
    assert [e["kind"] for e in history] == ["object.restore", "object.edit"]


@pytest.mark.parametrize(
    "changes,expected,status",
    [
        ({"id": "z"}, {"id": "a"}, 400),
        ({"parent": "b"}, {"parent": "a"}, 400),
        ({"score": "wrong"}, {"score": 10.0}, 400),
        ({"active": "false"}, {"active": True}, 400),
        ({"count": 1.5}, {"count": 1}, 400),
        ({"missing": 2}, {"missing": None}, 400),
        ({"name": "changed"}, {"name": "stale"}, 409),
        ({"name": "changed"}, None, 409),
    ],
)
def test_invalid_edits_and_conflicts_are_rejected(workspace, changes, expected, status):
    c, _, api = workspace
    assert (
        api.post("/api/management/objects/Item/a", json={"changes": changes, "expected": expected}).status_code
        == status
    )
    assert c.get("Item", "a")["name"] == "Alpha"
    assert api.get("/api/management/history").json()["entries"] == []


def test_metadata_is_validated_persisted_and_conflict_checked(workspace):
    c, path, api = workspace
    before = hashes(c.cfg.layers.root)
    body = {
        "revision": management.revision(path),
        "changes": {"description": "New meaning", "display_name": "Confidence"},
    }
    result = management.save_metadata("Item", body, "score", path)
    assert load(path).object_types["Item"].properties["score"].description == "New meaning"
    assert load(path).object_types["Item"].properties["score"].display_name == "Confidence"
    assert c.ontology.object_types["Item"].properties["score"].display_name == "Confidence"
    assert result["revision"] != body["revision"]
    with pytest.raises(Exception) as error:
        management.save_metadata("Item", body, "score", path)
    assert error.value.status_code == 409
    for changes in ({"type": "string"}, {"color": "red"}, {"title": "missing"}, {"group": "missing"}):
        with pytest.raises(Exception) as error:
            management.save_metadata("Item", {"revision": management.revision(path), "changes": changes}, path=path)
        assert error.value.status_code == 400
    assert hashes(c.cfg.layers.root) == before


def test_strings_are_not_interpreted_as_sql(workspace):
    c, _, _ = workspace
    value = "x'); DROP VIEW Item; --"
    edit_record(c, "Item", "a", {"name": value}, {"name": "Alpha"})
    assert c.get("Item", "a")["name"] == value
    assert c.objects("Item").count() == 2


def test_lineage_reports_external_layers_and_override_boundary(workspace):
    _, _, api = workspace
    d = api.get("/api/management/lineage").json()
    nodes = {n["id"]: n for n in d["nodes"]}
    assert not nodes["carelink"]["available"]
    assert nodes["object/Item"]["available"]
    assert {"source": "overrides", "target": "object/Item", "kind": "override"} in d["edges"]
    assert all(
        e["source"] != "overrides" for e in d["edges"] if nodes[e["target"]]["layer"] in {"raw", "transformed", "clean"}
    )


def test_restoring_with_stale_values_is_rejected(workspace):
    c, _, _ = workspace
    edit_record(c, "Item", "a", {"score": 50.0}, {"score": 10.0})
    with pytest.raises(RuntimeError):
        reset_record(c, "Item", "a", {"score": 10.0})
    assert c.get("Item", "a")["score"] == 50.0


def test_cross_origin_writes_are_rejected():
    from om_api.main import app

    response = TestClient(app).post(
        "/api/management/objects/Day/2026-08-14", json={}, headers={"Origin": "https://unrelated.example"}
    )
    assert response.status_code == 403
