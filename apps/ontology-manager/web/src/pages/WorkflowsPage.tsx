/**
 * Workflows: the ideation board for the application layer. Rendered from apps/ontology-manager/workflows.yaml;
 * every object type and action links back into the ontology, so ideas stay grounded in data that exists.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useOntology, useWorkflows } from "../api/client";
import type { Workflow } from "../api/types";
import { TypeIcon } from "../components/TypeIcon";
import { Loader, Segmented } from "../components/ui";

const PILLAR = {
  glucose: { label: "Glucose", color: "#34c77b" },
  recovery: { label: "Sleep & recovery", color: "#818cf8" },
  connections: { label: "Connections", color: "#f59e0b" },
  platform: { label: "Platform", color: "#38bdf8" },
} as const;
const STATUS = { idea: "", prototype: "accent", live: "good" } as const;

function WorkflowCard({ w }: { w: Workflow }) {
  const navigate = useNavigate();
  const { data: s } = useOntology();
  const typeOf = (n: string) => s?.object_types.find((t) => t.name === n);
  const p = PILLAR[w.pillar] ?? PILLAR.platform;
  return (
    <article className="glass workflow">
      <header className="spread" style={{ alignItems: "flex-start" }}>
        <div>
          <span className="pillar-tag" style={{ color: p.color }}><span className="dot" style={{ background: p.color }} />{p.label}</span>
          <h3 className="workflow-title">{w.title}</h3>
          {w.trigger && <div className="faint" style={{ fontSize: 12 }}>⏱ {w.trigger}</div>}
        </div>
        <span className={`chip ${STATUS[w.status] ?? ""}`}>{w.status}</span>
      </header>
      {w.agent && <p className="workflow-agent"><b>Agent:</b> {w.agent}</p>}
      {w.evidence && <p className="workflow-evidence">{w.evidence}</p>}
      {w.steps && (
        <ol className="workflow-steps">{w.steps.map((step) => <li key={step}>{step}</li>)}</ol>
      )}
      {w.visuals && (
        <div className="workflow-row"><span className="faint">Visuals</span><span className="row" style={{ gap: 4 }}>{w.visuals.map((v) => <span key={v} className="chip">{v}</span>)}</span></div>
      )}
      <div className="workflow-row">
        <span className="faint">Reads</span>
        <span className="row" style={{ gap: 4 }}>
          {(w.reads ?? []).map((r) => {
            const t = typeOf(r);
            return (
              <button key={r} className={`chip ${t ? "" : "bad"}`} style={{ cursor: "pointer" }} onClick={() => t && navigate(`/object-types/${r}`)}>
                {t && <TypeIcon icon={t.icon} color={t.color} size={16} />}{r}
              </button>
            );
          })}
        </span>
      </div>
      {w.writes && w.writes.length > 0 && (
        <div className="workflow-row">
          <span className="faint">Writes</span>
          <span className="row" style={{ gap: 4 }}>
            {w.writes.map((a) => <button key={a} className={`chip ${w.unknown.includes(a) ? "bad" : "accent"}`} style={{ cursor: "pointer" }} onClick={() => navigate("/action-types")}>⚡ {a}</button>)}
          </span>
        </div>
      )}
      {w.unknown.length > 0 && <div className="error-box" style={{ fontSize: 12 }}>Not in the ontology: {w.unknown.join(", ")}</div>}
    </article>
  );
}

export function WorkflowsPage() {
  const q = useWorkflows();
  const schema = useOntology();
  const [pillar, setPillar] = useState<string>("all");
  return (
    <>
      <div className="om-crumbs">Ideate / Workflows</div>
      <h1 className="page-title" style={{ margin: "4px 0 2px" }}>Workflows</h1>
      <p className="page-sub" style={{ marginBottom: 14 }}>
        The application layer to build on the ontology: what triggers each workflow, what it reads and writes, the visuals it needs and what an agent does in it.
      </p>
      <Loader query={q} height={300}>
        {(d) => {
          const items = d.workflows.filter((w) => pillar === "all" || w.pillar === pillar);
          const usage = new Map<string, number>();
          d.workflows.forEach((w) => (w.reads ?? []).forEach((r) => usage.set(r, (usage.get(r) ?? 0) + 1)));
          const types = schema.data?.object_types ?? [];
          const unused = types.filter((t) => !usage.has(t.name));
          return (
            <>
              <div className="row" style={{ marginBottom: 14 }}>
                <Segmented value={pillar} onChange={setPillar}
                  options={[{ value: "all", label: `All ${d.workflows.length}` }, ...Object.entries(PILLAR).map(([k, v]) => ({ value: k, label: v.label }))]} />
                <span className="faint" style={{ fontSize: 12 }}>Add or edit ideas in <code>{d.file}</code>; the page reloads them.</span>
              </div>
              <div className="workflow-grid">{items.map((w) => <WorkflowCard key={w.id} w={w} />)}</div>
              <section className="glass card" style={{ marginTop: 18 }}>
                <h3 className="card-title">Ontology coverage</h3>
                <p className="card-sub" style={{ marginBottom: 10 }}>How many workflow ideas use each object type. Unused types are open territory.</p>
                <div className="coverage">
                  {[...types].sort((a, b) => (usage.get(b.name) ?? 0) - (usage.get(a.name) ?? 0)).map((t) => (
                    <div key={t.name} className="coverage-row">
                      <span className="row" style={{ gap: 6, flexWrap: "nowrap" }}><TypeIcon icon={t.icon} color={t.color} size={18} />{t.name}</span>
                      <div className="insight-track"><div style={{ width: `${((usage.get(t.name) ?? 0) / Math.max(d.workflows.length, 1)) * 100}%`, background: t.color }} /></div>
                      <span className="num faint">{usage.get(t.name) ?? 0}</span>
                    </div>
                  ))}
                </div>
                {unused.length > 0 && <p className="faint" style={{ fontSize: 12, marginTop: 10 }}>Not used yet: {unused.map((t) => t.name).join(", ")}</p>}
              </section>
            </>
          );
        }}
      </Loader>
    </>
  );
}
