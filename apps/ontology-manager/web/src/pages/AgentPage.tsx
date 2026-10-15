/**
 * Agent tools: the ontology as typed tools an LLM agent can call. Inspect each tool's JSON Schema, try a call
 * exactly as an agent would (POST /api/agent/call), and copy the definitions + ontology primer into an agent.
 */

import { useMemo, useState } from "react";
import { getJson, useAgentCall, useAgentContext, useAgentTools } from "../api/client";
import type { AgentTool } from "../api/types";
import { DataTable, type Column } from "../components/DataTable";
import { Loader } from "../components/ui";
import { fmt } from "./ObjectsBrowser";

const EXAMPLES: Record<string, unknown> = {
  list_object_types: {},
  describe_object_type: { object_type: "Meal" },
  query_objects: {
    object_type: "Day",
    where: [{ property: "is_valid_cgm_day", op: "eq", value: true }],
    order_by: "tir", descending: false, properties: ["date_local", "tir", "mean_sg_mgdl", "tdd_u", "carbs_g"], limit: 10,
  },
  get_object: { object_type: "Day", primary_key: "2026-08-14" },
  search_around: {
    object_type: "Meal",
    where: [{ property: "meal_slot", op: "eq", value: "lunch" }, { property: "rise_to_peak_mgdl", op: "gt", value: 100 }],
    link: "meal_bolus", limit: 10,
  },
  aggregate: {
    object_type: "Meal", group_by: ["meal_slot"],
    metrics: [{ op: "count" }, { op: "median", property: "rise_to_peak_mgdl" }, { op: "avg", property: "carbs_g" }],
  },
  run_sql: {
    sql: "SELECT CASE WHEN sg_at_bedtime_mgdl > 180 THEN 'bed > 180' ELSE 'bed <= 180' END AS bedtime, count(*) AS nights, round(avg(tir), 3) AS overnight_tir FROM \"SleepSession\" WHERE sleep_type = 'long_sleep' AND cgm_coverage >= 0.7 GROUP BY 1",
  },
  create_experiment: { title: "Bedtime check + correction", metric: "overnight_tir", better: "higher", start_date: "2026-10-15", end_date: "2026-10-28", hypothesis: "Correcting before bed raises overnight TIR" },
  update_experiment: { experiment_id: "<id from create_experiment>", status: "completed", notes: "Worked on most nights" },
  add_day_note: { date_local: "2026-10-14", text: "Felt run-down; higher insulin needs", tags: "illness" },
};

const SNIPPET = `# A minimal Claude agent over this ontology (pip install anthropic requests)
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
    results = []
    for call in calls:  # write tools (actions) need confirm=True: ask the user first
        r = requests.post(f"{API}/agent/call", json={"tool": call.name, "args": call.input})
        results.append({"type": "tool_result", "tool_use_id": call.id, "content": r.text, "is_error": not r.ok})
    messages.append({"role": "user", "content": results})

print(reply.content[0].text)`;

function copy(text: string) {
  navigator.clipboard?.writeText(text).catch(() => undefined);
}

function ResultView({ result }: { result: unknown }) {
  const rows = (result as { rows?: Record<string, unknown>[] })?.rows ?? (Array.isArray(result) ? (result as Record<string, unknown>[]) : null);
  const columns = useMemo<Column<Record<string, unknown>>[]>(
    () => (rows?.length ? Object.keys(rows[0]).map((k) => ({ key: k, header: k, width: 150, render: (r) => <span>{fmt(r[k])}</span> })) : []),
    [rows],
  );
  const meta = rows && result && !Array.isArray(result) ? Object.fromEntries(Object.entries(result as object).filter(([k]) => k !== "rows")) : null;
  return (
    <div className="stack" style={{ gap: 10 }}>
      {meta && Object.keys(meta).length > 0 && <pre className="json">{JSON.stringify(meta, null, 2)}</pre>}
      {rows && rows.length > 0 && typeof rows[0] === "object" ? (
        <DataTable columns={columns} rows={rows} height={Math.min(380, 40 + rows.length * 34)} rowHeight={32} />
      ) : (
        <pre className="json">{JSON.stringify(result, null, 2)}</pre>
      )}
    </div>
  );
}

function ToolRunner({ tool }: { tool: AgentTool }) {
  const [args, setArgs] = useState(() => JSON.stringify(EXAMPLES[tool.name] ?? {}, null, 2));
  const [confirm, setConfirm] = useState(false);
  const call = useAgentCall();
  let parseError: string | null = null;
  try {
    JSON.parse(args);
  } catch (e) {
    parseError = (e as Error).message;
  }
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="spread" style={{ alignItems: "flex-start" }}>
        <div>
          <h2 className="mono" style={{ margin: 0, fontSize: 17 }}>{tool.name}</h2>
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>{tool.description}</p>
        </div>
        <span className={`chip ${tool.kind === "write" ? "warn" : "good"}`}>{tool.kind}</span>
      </div>
      <details>
        <summary className="faint" style={{ cursor: "pointer", fontSize: 12 }}>Input schema</summary>
        <pre className="json">{JSON.stringify(tool.input_schema, null, 2)}</pre>
      </details>
      <label className="action-label">Arguments (JSON)</label>
      <textarea className="sql-editor" style={{ minHeight: 150 }} spellCheck={false} value={args} onChange={(e) => setArgs(e.target.value)} />
      <div className="row">
        {tool.kind === "write" && (
          <label className="toggle"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /><span className="track" />I confirm this write</label>
        )}
        <div style={{ flex: 1 }} />
        {parseError && <span className="bad-text" style={{ fontSize: 12 }}>{parseError}</span>}
        <button className="btn primary" disabled={!!parseError || call.isPending}
          onClick={() => call.mutate({ tool: tool.name, args: JSON.parse(args), confirm })}>
          {call.isPending ? "Calling…" : "Call tool"}
        </button>
      </div>
      {call.error && <div className="error-box">{call.error.message}</div>}
      {call.data && <ResultView result={call.data.result} />}
    </div>
  );
}

export function AgentPage() {
  const tools = useAgentTools();
  const ctx = useAgentContext();
  const [pick, setPick] = useState("aggregate");
  const [copied, setCopied] = useState<string | null>(null);
  const done = (what: string) => { setCopied(what); setTimeout(() => setCopied(null), 1500); };
  return (
    <>
      <div className="om-crumbs">Ideate / Agent tools</div>
      <h1 className="page-title" style={{ margin: "4px 0 2px" }}>Agent tools</h1>
      <p className="page-sub" style={{ marginBottom: 14 }}>
        The ontology as typed tools for an LLM agent, generated from <code>ontology.yaml</code>: reads are safe; writes are the ontology's actions and need explicit confirmation. Try a call exactly as an agent would.
      </p>
      <div className="row" style={{ marginBottom: 14 }}>
        <button className="btn" onClick={async () => { copy(JSON.stringify(await getJson("/agent/tools", { format: "anthropic" }), null, 2)); done("Claude tools"); }}>Copy tools (Claude API)</button>
        <button className="btn" onClick={async () => { copy(JSON.stringify(await getJson("/agent/tools", { format: "openai" }), null, 2)); done("OpenAI tools"); }}>Copy tools (OpenAI format)</button>
        <button className="btn" onClick={() => { if (ctx.data) { copy(ctx.data.markdown); done("system prompt"); } }}>Copy ontology primer (system prompt)</button>
        <button className="btn" onClick={() => { copy(SNIPPET); done("agent loop"); }}>Copy example agent loop (Python)</button>
        {copied && <span className="chip good">Copied {copied}</span>}
      </div>
      <Loader query={tools} height={400}>
        {(list) => {
          const tool = list.find((t) => t.name === pick) ?? list[0];
          return (
            <div className="agent">
              <aside className="glass card">
                {(["read", "write"] as const).map((kind) => (
                  <div key={kind}>
                    <div className="om-section" style={{ paddingLeft: 4 }}>{kind === "read" ? "Read tools" : "Write tools (actions)"}</div>
                    <div className="type-list">
                      {list.filter((t) => t.kind === kind).map((t) => (
                        <div key={t.name} className={`type-item ${t.name === tool.name ? "on" : ""}`} onClick={() => setPick(t.name)}>
                          <span className="mono" style={{ fontSize: 12.5 }}>{t.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </aside>
              <section className="glass card"><ToolRunner key={tool.name} tool={tool} /></section>
            </div>
          );
        }}
      </Loader>
      <details className="glass card" style={{ marginTop: 16 }}>
        <summary className="card-title" style={{ cursor: "pointer" }}>Ontology primer (what an agent gets as its system prompt)</summary>
        <pre className="json" style={{ marginTop: 10, maxHeight: 420 }}>{ctx.data?.markdown ?? "Loading…"}</pre>
      </details>
      <details className="glass card" style={{ marginTop: 12 }}>
        <summary className="card-title" style={{ cursor: "pointer" }}>Example: a Claude agent loop over these tools</summary>
        <pre className="json" style={{ marginTop: 10 }}>{SNIPPET}</pre>
      </details>
    </>
  );
}
