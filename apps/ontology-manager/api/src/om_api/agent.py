"""Agent tools: the ontology exposed as typed tools an LLM agent can call (the seed of "embedded intelligence").

Everything is generated from ontology.yaml, so a new object type, link or action becomes a tool (or a valid
argument to one) without code changes:

  read tools   list_object_types, describe_object_type, query_objects, get_object, search_around, aggregate, run_sql
  write tools  one per action type (create_experiment, add_day_note, ...): require explicit confirmation

GET  /api/agent/tools?format=anthropic|openai|full   tool definitions (JSON Schema), ready for an LLM API
POST /api/agent/call {tool, args, confirm}            execute one tool call, exactly as an agent would
GET  /api/agent/context                               an ontology primer (markdown) for an agent's system prompt
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from t1d_ontology.actions import ActionError

from om_api.actions import apply as apply_action
from om_api.db import client, cursor, query, records
from om_api.objects import object_with_links, where_clause
from om_api.ontology_routes import object_type
from om_api.sql import run_select

router = APIRouter(tags=["agent"])
MAX_ROWS = 200
JSON_TYPE = {
    "string": {"type": "string"}, "integer": {"type": "integer"}, "double": {"type": "number"},
    "boolean": {"type": "boolean"}, "date": {"type": "string", "format": "date"},
    "timestamp": {"type": "string", "format": "date-time"},
}  # fmt: skip
AGGS = {"count": "count", "sum": "sum", "avg": "avg", "min": "min", "max": "max", "median": "median"}

# Domain conventions an agent must know to reason correctly (also in the repo README).
CONVENTIONS = """\
- One person with type 1 diabetes: Medtronic MiniMed 780G pump (SmartGuard closed loop) + Abbott Instinct CGM, plus an Oura ring.
- `*_utc` columns are true UTC; `*_local` / `date_local` are local wall-clock time where the person was (home America/New_York, travels often; Day.is_travel_day).
- Use Day.is_valid_cgm_day (>= 70% CGM coverage, not partial) for daily glucose metrics.
- Glucose ranges (mg/dL): very low < 54 <= low < 70 <= in range <= 180 < high <= 250 < very high. TIR = share of time 70-180 (target > 70%); TBR < 4%.
- OuraDay(d) describes the night ending on the morning of d (Oura dates a night by the wake-up day).
- tdd_u = bolus_u + auto_insulin_u. The CareLink CSV under-counts SmartGuard auto-corrections (~5-7 U/day).
- Meals are Bolus Wizard carb entries only. trend_at_meal_mgdl_per_min > 0 means glucose was already rising at the bolus (late pre-bolus).
- Findings are associations in one person's data, not causal claims; report n alongside any comparison. Not medical advice: suggest discussing therapy changes with the endocrinologist."""


def _type_names(datasets: bool = True) -> list[str]:
    return [t.name for t in client().ontology.object_types.values() if datasets or not t.is_dataset]


def _where_schema() -> dict:
    return {
        "type": "array",
        "description": "Filters, AND-ed. op: eq ne gt gte lt lte contains isnull notnull",
        "items": {
            "type": "object",
            "properties": {
                "property": {"type": "string"},
                "op": {
                    "type": "string",
                    "enum": ["eq", "ne", "gt", "gte", "lt", "lte", "contains", "isnull", "notnull"],
                },
                "value": {"description": "Compared value (omit for isnull / notnull)"},
            },
            "required": ["property", "op"],
        },
    }


def tool_specs() -> list[dict]:
    ont = client().ontology
    types = _type_names()
    t = {"type": "string", "enum": types, "description": "Object type API name"}
    specs: list[dict] = [
        {"name": "list_object_types", "kind": "read",
         "description": "List every object type in the ontology with its description, group and object count.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "describe_object_type", "kind": "read",
         "description": "Properties (name, type, description), primary key, links and actions of one object type. Call this before querying a type you haven't seen.",
         "input_schema": {"type": "object", "properties": {"object_type": t}, "required": ["object_type"]}},
        {"name": "query_objects", "kind": "read",
         "description": "Fetch objects of one type with filters, ordering and a row limit. Prefer `aggregate` for statistics.",
         "input_schema": {"type": "object", "properties": {
             "object_type": t, "where": _where_schema(),
             "order_by": {"type": "string"}, "descending": {"type": "boolean", "default": True},
             "properties": {"type": "array", "items": {"type": "string"}, "description": "Subset of properties to return (default: all)"},
             "limit": {"type": "integer", "default": 20, "maximum": MAX_ROWS}},
             "required": ["object_type"]}},
        {"name": "get_object", "kind": "read",
         "description": "One object by primary key, with every linked object (first 20 per link).",
         "input_schema": {"type": "object", "properties": {"object_type": t, "primary_key": {"type": "string"}},
                          "required": ["object_type", "primary_key"]}},
        {"name": "search_around", "kind": "read",
         "description": "Follow a link type from a filtered set of objects to the objects on the other side, e.g. Meal (lunch) -> meal_bolus -> Bolus.",
         "input_schema": {"type": "object", "properties": {
             "object_type": t, "where": _where_schema(),
             "link": {"type": "string", "enum": list(ont.link_types), "description": "Link type API name"},
             "limit": {"type": "integer", "default": 20, "maximum": MAX_ROWS}},
             "required": ["object_type", "link"]}},
        {"name": "aggregate", "kind": "read",
         "description": "Group and aggregate one object type: count / sum / avg / min / max / median of properties, optionally filtered.",
         "input_schema": {"type": "object", "properties": {
             "object_type": t, "where": _where_schema(),
             "group_by": {"type": "array", "items": {"type": "string"}},
             "metrics": {"type": "array", "items": {"type": "object", "properties": {
                 "op": {"type": "string", "enum": list(AGGS)}, "property": {"type": "string", "description": "Omit for count(*)"}},
                 "required": ["op"]}},
             "limit": {"type": "integer", "default": 50, "maximum": MAX_ROWS}},
             "required": ["object_type", "metrics"]}},
        {"name": "run_sql", "kind": "read",
         "description": 'Read-only DuckDB SQL over the ontology (tables are named after object types, quoted: "Day", "Meal"). One SELECT only. Use for joins across types.',
         "input_schema": {"type": "object", "properties": {"sql": {"type": "string"},
                                                           "limit": {"type": "integer", "default": 100, "maximum": MAX_ROWS}},
                          "required": ["sql"]}},
    ]  # fmt: skip
    for a in ont.action_types.values():
        props: dict[str, Any] = {}
        for p in a.parameters.values():
            props[p.name] = dict(JSON_TYPE[p.type]) | ({"enum": list(p.enum)} if p.enum else {})
        specs.append({
            "name": a.name, "kind": "write",
            "description": f"{a.description} ({a.kind}s a {a.object_type}). WRITE: only call after the user agreed.",
            "input_schema": {"type": "object", "properties": props,
                             "required": [p.name for p in a.parameters.values() if p.required]},
        })  # fmt: skip
    return specs


def _filters(ot, where: list[dict] | None) -> tuple[str, list]:
    return where_clause(ot, [(w.get("property"), w.get("op"), w.get("value")) for w in where or []])


def _limit(args: dict, default: int) -> int:
    return max(1, min(int(args.get("limit") or default), MAX_ROWS))


def call(cur, tool: str, args: dict, confirm: bool = False) -> Any:
    ont = client().ontology
    if tool == "list_object_types":
        return [
            {"object_type": t.name, "group": t.group, "kind": "time series" if t.is_dataset else "object",
             "description": t.description, "count": cur.execute(f'SELECT count(*) FROM "{t.name}"').fetchone()[0]}
            for t in ont.object_types.values()
        ]  # fmt: skip
    if tool == "describe_object_type":
        t = object_type(args["object_type"])
        return {
            "object_type": t.name, "description": t.description, "primary_key": t.primary_key, "title": t.title,
            "properties": [{"name": p.name, "type": p.type, "description": p.description} for p in t.properties.values()],
            "links": [{"link": lt.name, "to": lt.one if lt.many == t.name else lt.many,
                       "cardinality": "many-to-one" if lt.many == t.name else "one-to-many",
                       "join": f"{lt.many}.{lt.foreign_key} = {lt.one}.{ont.object_types[lt.one].primary_key}"}
                      for lt in ont.links_of(t.name)],
            "actions": [a.name for a in ont.action_types.values() if a.object_type == t.name],
        }  # fmt: skip
    if tool == "query_objects":
        t = object_type(args["object_type"])
        where, params = _filters(t, args.get("where"))
        cols = [c for c in args.get("properties") or [] if c in t.properties] or list(t.properties)
        order = args.get("order_by") if args.get("order_by") in t.properties else (t.title or t.primary_key)
        sql = (f'SELECT {", ".join(f"{chr(34)}{c}{chr(34)}" for c in cols)} FROM "{t.name}" WHERE {where} '
               f'ORDER BY "{order}" {"DESC" if args.get("descending", True) else "ASC"} NULLS LAST LIMIT {_limit(args, 20)}')  # fmt: skip
        total = cur.execute(f'SELECT count(*) FROM "{t.name}" WHERE {where}', params).fetchone()[0]
        return {"total_matching": total, "rows": records(query(cur, sql, params))}
    if tool == "get_object":
        return object_with_links(cur, object_type(args["object_type"]), str(args["primary_key"]), link_limit=20)
    if tool == "search_around":
        t = object_type(args["object_type"])
        lt = ont.link_types.get(args.get("link", ""))
        if lt is None or t.name not in (lt.many, lt.one):
            raise ValueError(f"link {args.get('link')!r} does not touch {t.name}; see describe_object_type")
        where, params = _filters(t, args.get("where"))
        if lt.many == t.name:  # many -> one: the objects these point at
            target = ont.object_types[lt.one]
            sql = (f'SELECT * FROM "{target.name}" WHERE "{target.primary_key}" IN '
                   f'(SELECT "{lt.foreign_key}" FROM "{t.name}" WHERE {where})')  # fmt: skip
        else:  # one -> many: the objects pointing at these
            target = ont.object_types[lt.many]
            sql = (f'SELECT * FROM "{target.name}" WHERE "{lt.foreign_key}" IN '
                   f'(SELECT "{t.primary_key}" FROM "{t.name}" WHERE {where})')  # fmt: skip
        total = cur.execute(f"SELECT count(*) FROM ({sql})", params).fetchone()[0]
        return {"object_type": target.name, "total_matching": total,
                "rows": records(query(cur, f"{sql} LIMIT {_limit(args, 20)}", params))}  # fmt: skip
    if tool == "aggregate":
        t = object_type(args["object_type"])
        where, params = _filters(t, args.get("where"))
        groups = [g for g in args.get("group_by") or [] if g in t.properties]
        if len(groups) != len(args.get("group_by") or []):
            raise ValueError("group_by contains unknown properties")
        exprs = []
        for m in args.get("metrics") or [{"op": "count"}]:
            op, prop = m.get("op"), m.get("property")
            if op not in AGGS or (prop is not None and prop not in t.properties):
                raise ValueError(f"bad metric {m}")
            exprs.append("count(*) AS n" if op == "count" and not prop else f'{AGGS[op]}("{prop}") AS {op}_{prop}')
        g = ", ".join(f'"{c}"' for c in groups)
        sql = f'SELECT {g + ", " if g else ""}{", ".join(exprs)} FROM "{t.name}" WHERE {where}'
        if g:
            sql += f" GROUP BY {g} ORDER BY {g}"
        return {"rows": records(query(cur, f"{sql} LIMIT {_limit(args, 50)}", params))}
    if tool == "run_sql":
        return run_select(cur, str(args.get("sql", "")), _limit(args, 100))
    if tool in ont.action_types:
        if not confirm:
            raise PermissionError(
                f"{tool} writes to the ontology; repeat the call with confirm=true once the user agreed"
            )
        return apply_action(tool, args)
    raise ValueError(f"unknown tool {tool}")


@router.get("/agent/tools")
def tools(format: str = Query("full", pattern="^(full|anthropic|openai)$")) -> list[dict]:
    specs = tool_specs()
    if format == "anthropic":
        return [{"name": s["name"], "description": s["description"], "input_schema": s["input_schema"]} for s in specs]
    if format == "openai":
        return [{"type": "function", "function": {"name": s["name"], "description": s["description"],
                                                  "parameters": s["input_schema"]}} for s in specs]  # fmt: skip
    return specs


@router.post("/agent/call")
def agent_call(body: dict = Body(...), cur=Depends(cursor)) -> dict:  # noqa: B008
    tool, args = body.get("tool"), body.get("args") or {}
    try:
        return {"tool": tool, "result": jsonable_encoder(call(cur, tool, args, bool(body.get("confirm"))))}
    except PermissionError as e:
        raise HTTPException(403, str(e)) from None
    except (ValueError, KeyError, ActionError) as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}") from None


@router.get("/agent/context")
def context(cur=Depends(cursor)) -> dict:
    """A compact ontology primer for an agent's system prompt."""
    ont = client().ontology
    lines = [f"# Ontology `{ont.name}` v{ont.version}", "", "## Conventions", CONVENTIONS, "", "## Object types"]
    for t in ont.object_types.values():
        n = cur.execute(f'SELECT count(*) FROM "{t.name}"').fetchone()[0]
        props = ", ".join(f"{p.name}:{p.type}" for p in t.properties.values())
        lines += [
            f"### {t.name} ({n:,} {'rows' if t.is_dataset else 'objects'}; pk {t.primary_key})",
            t.description,
            f"Properties: {props}",
            "",
        ]
    lines += ["## Link types (many -> one)"]
    lines += [f"- {lt.name}: {lt.many}.{lt.foreign_key} -> {lt.one}" for lt in ont.link_types.values()]
    lines += ["", "## Actions (writes; ask the user first)"]
    lines += [f"- {a.name}: {a.description}" for a in ont.action_types.values()]
    return {"markdown": "\n".join(lines)}
