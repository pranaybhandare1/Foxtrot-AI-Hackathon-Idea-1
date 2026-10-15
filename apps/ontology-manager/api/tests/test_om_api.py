"""Ontology Manager API: metadata, objects, profiles, read-only SQL, agent tools and workflows."""

import pytest
from fastapi.testclient import TestClient
from om_api.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    "path",
    ["/api/ontology", "/api/objects/Meal?limit=5", "/api/objects/Day/2026-08-14", "/api/objects/Meal/profile",
     "/api/agent/tools", "/api/agent/tools?format=anthropic", "/api/agent/tools?format=openai", "/api/agent/context",
     "/api/workflows"],
)  # fmt: skip
def test_endpoints_respond(path):
    assert client.get(path).status_code == 200


def test_ontology_metadata_is_complete():
    body = client.get("/api/ontology").json()
    names = {t["name"] for t in body["object_types"]}
    assert {"Day", "Meal", "OuraDay", "Experiment"} <= names
    assert all(lt["many"] in names and lt["one"] in names for lt in body["link_types"])


def test_profile_has_categorical_top_values():
    prof = client.get("/api/objects/Meal/profile").json()["properties"]["meal_slot"]
    assert {v["value"] for v in prof["top"]} <= {"breakfast", "lunch", "dinner", "late_night"}


@pytest.mark.parametrize(
    "sql",
    ['DROP VIEW "Meal"', "COPY (SELECT 1) TO 'x.csv'", "SELECT 1; SELECT 2", "ATTACH 'x.db'", "not sql"],
)
def test_sql_is_read_only(sql):
    assert client.post("/api/sql", json={"sql": sql}).status_code == 400


def test_sql_select_works():
    r = client.post("/api/sql", json={"sql": 'SELECT meal_slot, count(*) AS n FROM "Meal" GROUP BY 1'}).json()
    assert r["columns"][0]["name"] == "meal_slot" and r["rows"]


def test_every_action_is_a_write_tool_and_reads_are_marked():
    tools = {t["name"]: t for t in client.get("/api/agent/tools").json()}
    actions = {a["name"] for a in client.get("/api/ontology").json()["action_types"]}
    assert actions and all(tools[a]["kind"] == "write" for a in actions)
    assert tools["aggregate"]["kind"] == "read"


def test_agent_read_tools():
    call = lambda tool, args: client.post("/api/agent/call", json={"tool": tool, "args": args})  # noqa: E731
    agg = call("aggregate", {"object_type": "Meal", "group_by": ["meal_slot"], "metrics": [{"op": "count"}]}).json()
    assert sum(r["n"] for r in agg["result"]["rows"]) == client.get("/api/objects/Meal?limit=1").json()["total"]
    around = call("search_around", {"object_type": "Meal", "link": "meal_bolus", "limit": 3}).json()["result"]
    assert around["object_type"] == "Bolus" and around["total_matching"] > 0
    assert (
        call(
            "query_objects", {"object_type": "Meal", "where": [{"property": "nope", "op": "eq", "value": 1}]}
        ).status_code
        == 400
    )
    assert call("unknown_tool", {}).status_code == 400


def test_write_tools_require_confirmation():
    r = client.post("/api/agent/call", json={"tool": "add_day_note", "args": {"date_local": "2026-10-01", "text": "x"}})
    assert r.status_code == 403


def test_workflows_reference_real_ontology_entities():
    for w in client.get("/api/workflows").json()["workflows"]:
        assert w["unknown"] == [], (w["id"], w["unknown"])
        assert all(isinstance(s, str) for s in w["steps"])
