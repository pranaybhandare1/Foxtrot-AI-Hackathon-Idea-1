# Kaizen · Ontology Manager

A Palantir Foundry Ontology Manager look-alike over the Kaizen health ontology. Use it to **understand the data**
(what each object type is, how it links and what its values look like) and to **ideate what to build** on it:
workflows, visuals and agents.

```bash
make setup   # from the repo root, once
make om      # build the UI and serve http://127.0.0.1:8770   (API docs: /api/docs)
```

Develop with hot reload: `make om-api` (API on :8770) and `make om-dev` (UI on :5174) in two terminals.
Node comes from the `nodejs-wheel` dev dependency, so no system Node install is needed.

## What's in it

| Area | Page | Notes |
|---|---|---|
| Discover | **Discover** | Object types as cards, grouped (Calendar, Glucose, Insulin & meals, Devices & pump, Sleep & recovery, Lifestyle) |
| Resources | **Object types** | Table of all types → each type has tabs: **Overview** (metadata + link neighbourhood graph), **Properties** (display / API name, base type, keys, *live profile*: null %, distinct, range / median, top values), **Link types**, **Datasources** (lineage), **Actions** (run them), **Objects** (search, filter, open an object, follow links object to object) |
| | **Link types**, **Action types**, **Graph** | Every relationship; every write action with a generated form; force-directed ontology graph |
| Ideate | **Explore & visualize** | Read-only SQL (DuckDB) over the ontology with an auto chart (bar / line / scatter) and starter questions |
| | **Workflows** | Ideas from [`workflows.yaml`](workflows.yaml) rendered as cards: trigger, agent role, evidence, steps, visuals, reads / writes linked to the ontology, plus an ontology-coverage view |
| | **Agent tools** | The ontology as LLM tools: inspect schemas, call them, copy tool definitions (Claude / OpenAI format), the system-prompt primer and an example agent loop |

## Architecture

```
web/  React 19 + TypeScript + Vite + ECharts + TanStack Query   →  /api (JSON)
api/  FastAPI (om_api)                                           →  t1d_ontology SDK → DuckDB views → data/clean/*.parquet
      ontology_routes · objects · sql · actions · agent · workflows      writes: actions → data/writeback/
```

Everything is generated from `ontology/ontology.yaml`: add an object type, link or action there (and its data)
and it appears in every page and as an agent tool, with no app code changes.

### API

| Endpoint | |
|---|---|
| `GET /api/ontology` | groups, object types (properties, links, actions, counts, lineage), link types, action types |
| `GET /api/objects/{type}?filter=prop:op:value&q=&order_by=&desc=` | objects (ops: eq ne gt gte lt lte contains isnull notnull) |
| `GET /api/objects/{type}/{pk}` | one object + all linked objects |
| `GET /api/objects/{type}/profile` | per-property profile |
| `POST /api/sql {sql, limit}` | read-only SQL: one SELECT, checked by DuckDB's parser |
| `POST /api/actions/{name}` | run an action (typed, validated parameters) |
| `GET /api/agent/tools?format=full\|anthropic\|openai` | tool definitions |
| `POST /api/agent/call {tool, args, confirm}` | execute a tool call; write tools need `confirm: true` |
| `GET /api/agent/context` | ontology primer (markdown) for an agent's system prompt |
| `GET /api/workflows` | `workflows.yaml`, with references checked against the ontology |

## Agent tools

| Tool | Kind | What it does |
|---|---|---|
| `list_object_types` | read | Every type with description and count |
| `describe_object_type` | read | Properties, primary key, links (with join), actions |
| `query_objects` | read | Filtered, ordered, limited objects (≤ 200 rows) |
| `get_object` | read | One object + its linked objects |
| `search_around` | read | Follow a link from a filtered set, e.g. lunches with a > 100 mg/dL rise → their boluses |
| `aggregate` | read | count / sum / avg / min / max / median, grouped |
| `run_sql` | read | One read-only SELECT across types |
| `create_experiment`, `update_experiment`, `add_day_note` | **write** | The ontology's actions; refused (403) unless `confirm: true`, so the agent must ask the user first |

Minimal Claude loop (also copyable from the page):

```python
import anthropic, requests

API = "http://127.0.0.1:8770/api"
tools = requests.get(f"{API}/agent/tools", params={"format": "anthropic"}).json()
system = requests.get(f"{API}/agent/context").json()["markdown"]
client = anthropic.Anthropic()
messages = [{"role": "user", "content": "Why are my nights worse lately, and what should I try?"}]
while True:
    reply = client.messages.create(model="claude-opus-5-5", max_tokens=4096, system=system, tools=tools, messages=messages)
    messages.append({"role": "assistant", "content": reply.content})
    calls = [b for b in reply.content if b.type == "tool_use"]
    if not calls:
        break
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": c.id,
         "content": (r := requests.post(f"{API}/agent/call", json={"tool": c.name, "args": c.input})).text,
         "is_error": not r.ok}
        for c in calls]})
print(reply.content[0].text)
```

Agents get the same data the app does: keep the privacy note in the repo README in mind before sending it to any
hosted model.

## Adding a workflow idea

Append to [`workflows.yaml`](workflows.yaml) (fields documented at the top of the file) and reload the page.
Object types and actions you list are linked to the ontology, and anything that doesn't exist is flagged.
Quote values that contain a colon (`"Optional: …"`).

## Ideas for what to build next

- **Chat panel**: put the agent loop behind a chat UI in this app, with tool calls rendered as cards and
  write calls as confirm buttons.
- **Object views**: custom layouts per type (a Day timeline, a Meal response chart) instead of key/value lists.
- **Saved explorations**: save SQL + chart from Explore into a workflow's visuals.
- **Workflow runner**: turn a `prototype` workflow into a scheduled job that calls the agent tools.
