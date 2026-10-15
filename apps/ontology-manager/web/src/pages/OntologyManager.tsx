/**
 * Ontology Manager, modelled on Palantir Foundry's: a resource sidebar (Discover, Object types, Link types,
 * Action types, Graph) plus an Ideate section (Explore, Workflows, Agent tools); object-type pages with
 * Overview / Properties (with data profiles) / Link types / Datasources / Actions / Objects tabs.
 * Everything is generated from /api/ontology (i.e. ontology/ontology.yaml).
 */

import { useMemo, useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { useOntology, useProfile } from "../api/client";
import type { ActionType, ObjectType, OntologySchema, PropertyProfile } from "../api/types";
import { ActionDrawer } from "../components/ActionForm";
import { EChart } from "../components/EChart";
import { Icons } from "../components/Icons";
import { TypeIcon } from "../components/TypeIcon";
import { Loader } from "../components/ui";
import { tooltip } from "../lib/chartTheme";
import { num } from "../lib/format";
import { ObjectsBrowser } from "./ObjectsBrowser";
import { MetadataEditor, WorkspaceHome } from "./ManagerPages";

export const displayName = (api: string) => api.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/(\d+)([A-Z])/g, "$1 $2");
const propDisplay = (api: string) => {
  const s = api.replace(/_/g, " ").replace(/\b(utc|sg|tir|tbr|tar|tdd|cv|gmi|hrv|id|bg|pk)\b/g, (m) => m.toUpperCase());
  return s.charAt(0).toUpperCase() + s.slice(1);
};
const ago = (epoch: number | null) => {
  if (!epoch) return "–";
  const mins = Math.round((Date.now() / 1000 - epoch) / 60);
  return mins < 60 ? `${mins} min ago` : mins < 1440 ? `${Math.round(mins / 60)} h ago` : `${Math.round(mins / 1440)} days ago`;
};
const SOURCE_LABEL: Record<string, string> = { carelink: "CareLink", oura: "Oura", writeback: "Write-back" };
const TYPE_BADGE: Record<string, string> = { string: "String", integer: "Integer", double: "Double", boolean: "Boolean", date: "Date", timestamp: "Timestamp" };

function useOm() {
  const q = useOntology();
  return q;
}

/* ------------------------------------------------------------------ shell */

export function OntologyManager() {
  const q = useOm();
  const navigate = useNavigate();
  const [find, setFind] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const hits = useMemo(
    () => (find && q.data ? q.data.object_types.filter((t) => `${t.name} ${displayName(t.name)} ${t.description}`.toLowerCase().includes(find.toLowerCase())).slice(0, 8) : []),
    [find, q.data],
  );
  const item = (to: string, label: string, icon: ReactNode, count?: number, end = false) => (
    <NavLink to={to} end={end} className={({ isActive }) => `om-nav-item ${isActive ? "on" : ""}`}>
      {icon}<span>{label}</span>{count != null && <span className="om-count">{count}</span>}
    </NavLink>
  );
  return (
    <div className={`foundry-shell ${navOpen ? "nav-open" : ""}`}>
      <header className="foundry-topbar"><button className="sidebar-toggle" aria-label="Toggle resource navigation" aria-expanded={navOpen} onClick={() => setNavOpen(!navOpen)}><Icons.collapse /></button><NavLink to="/" className="foundry-wordmark"><svg className="brand-mark" width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden><circle cx="16" cy="16" r="12" stroke="currentColor" strokeWidth="1.6"/><path d="M8 17c5-9 13-9 16-2-6 8-11 8-16 2Z" stroke="currentColor" strokeWidth="1.6"/><path d="M9 23 23 9" stroke="currentColor" strokeWidth="1.3"/></svg> Kaizen</NavLink><span className="topbar-divider"/><span className="topbar-workspace">Personal Health Intelligence Workspace</span><div className="topbar-right"><span className="local-indicator"/> Local environment <span className="workspace-avatar" aria-label="Kaizen workspace">K</span></div></header>
      <nav className="foundry-rail" aria-label="Applications"><NavLink to="/" end title="Workspace overview"><Icons.overview/></NavLink><NavLink to="/object-types" title="Ontology Manager"><TypeIconSmall icon="cube"/></NavLink><NavLink to="/lineage" title="Data Lineage"><Icons.explorer/></NavLink><NavLink to="/properties" title="Property Manager"><Icons.history/></NavLink><NavLink to="/explore" title="Explore data"><Icons.weekly/></NavLink><div className="rail-bottom"><NavLink to="/history" title="Change history"><Icons.report/></NavLink></div></nav>
      <div className="om">
      <aside className="glass om-side" onClick={e => { if ((e.target as HTMLElement).closest("a")) setNavOpen(false); }}>
        <div className="om-brand">
          <TypeIcon icon="cube" color="#2d72d2" size={26} />
          <div>
            <div style={{ fontWeight: 700 }}>Ontology Manager</div>
            <div className="faint mono" style={{ fontSize: 11 }}>{q.data ? `${q.data.name} · v${q.data.version}` : "…"}</div>
          </div>
        </div>
        <div className="om-search">
          <Icons.search />
          <input placeholder="Search object types…" value={find} onChange={(e) => setFind(e.target.value)} />
        </div>
        {hits.length > 0 && (
          <div className="om-hits">
            {hits.map((t) => (
              <button key={t.name} onClick={() => { setFind(""); navigate(`/object-types/${t.name}`); }}>
                <TypeIcon icon={t.icon} color={t.color} size={20} />{displayName(t.name)}
              </button>
            ))}
          </div>
        )}
        <div className="om-section">Discover</div>
        {item("/", "Discover", <Icons.overview />, undefined, true)}
        <div className="om-section">Resources</div>
        {item("/object-types", "Object types", <TypeIconSmall icon="cube" />, q.data?.object_types.length)}
        {item("/link-types", "Link types", <TypeIconSmall icon="link" />, q.data?.link_types.length)}
        {item("/action-types", "Action types", <TypeIconSmall icon="bolt" />, q.data?.action_types.length)}
        {item("/properties", "Property Manager", <Icons.history />)}
        {item("/graph", "Ontology graph", <Icons.explorer />)}
        <div className="om-section">Data integration</div>
        {item("/lineage", "Data Lineage", <Icons.explorer />)}
        {item("/history", "Change history", <Icons.report />)}
        <div className="om-section">Ideate</div>
        {item("/explore", "Explore & visualize", <Icons.weekly />)}
        {item("/workflows", "Workflows", <Icons.daily />)}
        {item("/agent", "Agent tools", <Icons.agp />)}
        {q.data && (
          <>
            <div className="om-section">Groups</div>
            {q.data.groups.map((g) => (
              <NavLink key={g.name} to={`/object-types?group=${g.name}`} className="om-nav-item">
                <span className="om-group-dot" />{g.display_name}
                <span className="om-count">{q.data.object_types.filter((t) => t.group === g.name).length}</span>
              </NavLink>
            ))}
          </>
        )}
        <div style={{ flex: 1 }} />
        <div className="om-nav-item workspace-local"><Icons.quality /><span>Local workspace</span></div>
      </aside>
      <section className="om-main">
        <Loader query={q} height={400}>{() => <Outlet />}</Loader>
      </section>
      </div>
    </div>
  );
}

const TypeIconSmall = ({ icon }: { icon: string }) => (
  <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    {icon === "link" ? (<><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></>)
      : icon === "bolt" ? <path d="M13 2 4 14h7l-1 8 9-12h-7z" />
      : (<><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" /><path d="m4 7.5 8 4.5 8-4.5M12 12v9" /></>)}
  </svg>
);

const Crumbs = ({ items }: { items: { label: string; to?: string }[] }) => {
  const navigate = useNavigate();
  return (
    <div className="om-crumbs">
      {items.map((c, i) => (
        <span key={i}>
          {i > 0 && <span className="faint"> / </span>}
          {c.to ? <button onClick={() => navigate(c.to!)}>{c.label}</button> : <b>{c.label}</b>}
        </span>
      ))}
    </div>
  );
};

const schemaOf = (q: ReturnType<typeof useOm>) => q.data as OntologySchema;

/* ------------------------------------------------------------------ discover */

export function Discover() { return <WorkspaceHome />; }

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div><div className="faint" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".06em" }}>{label}</div><div style={{ fontWeight: 650 }}>{value}</div></div>
);

/* ------------------------------------------------------------------ graph */

export function OntologyGraph({ focus, height = 620 }: { focus?: string; height?: number }) {
  const s = schemaOf(useOm());
  const navigate = useNavigate();
  const types = focus
    ? s.object_types.filter((t) => t.name === focus || s.link_types.some((l) => (l.many === focus && l.one === t.name) || (l.one === focus && l.many === t.name)))
    : s.object_types;
  const names = new Set(types.map((t) => t.name));
  const links = s.link_types.filter((l) => names.has(l.many) && names.has(l.one));
  const body = (
    <EChart height={height} deps={[s, focus]} onClick={(e) => e.dataType === "node" && navigate(`/object-types/${e.name}`)}
      build={(p) => ({
        tooltip: tooltip(p, { trigger: "item",
          formatter: (i: any) => (i.dataType === "edge" ? `<b>${i.data.label}</b><br/>${i.data.source} → ${i.data.target} (many → one)` : `<b>${displayName(i.name)}</b><br/>${i.data.count.toLocaleString()} objects`) }),
        series: [{
          type: "graph", layout: "force", roam: true, draggable: true,
          force: { repulsion: focus ? 600 : 380, edgeLength: focus ? 180 : [90, 170], gravity: 0.08 },
          label: { show: true, position: "bottom", color: p.text, fontSize: 11.5, formatter: (i: any) => displayName(i.name) },
          edgeSymbol: ["none", "arrow"], edgeSymbolSize: 7,
          lineStyle: { color: p.faint, width: 1.2, opacity: 0.6, curveness: 0.12 },
          emphasis: { focus: "adjacency", lineStyle: { width: 2.4 } },
          data: types.map((t) => ({
            name: t.name, count: t.count,
            symbolSize: Math.max(16, Math.min(46, 8 + Math.log10(t.count + 1) * 8)) * (t.name === focus ? 1.3 : 1),
            itemStyle: { color: t.color, borderColor: "rgba(255,255,255,.7)", borderWidth: t.name === focus ? 3 : 1.5, shadowBlur: 10, shadowColor: `${t.color}88` },
          })),
          links: links.map((l) => ({ source: l.many, target: l.one, label: l.name })),
        }],
      })}
    />
  );
  if (focus) return body;
  return (
    <>
      <Crumbs items={[{ label: "Ontology", to: "/" }, { label: "Graph" }]} />
      <h1 className="page-title" style={{ margin: "4px 0 2px" }}>Ontology graph</h1>
      <p className="page-sub" style={{ marginBottom: 14 }}>Object types (sized by object count) and link types (arrows point many → one). Drag, scroll to zoom, click a type to open it.</p>
      <div className="glass card">{body}</div>
    </>
  );
}

/* ------------------------------------------------------------------ object types list */

export function ObjectTypesList() {
  const s = schemaOf(useOm());
  const navigate = useNavigate();
  const group = new URLSearchParams(window.location.search).get("group");
  const [q, setQ] = useState("");
  const rows = s.object_types.filter((t) => (!group || t.group === group) && `${t.name} ${t.description}`.toLowerCase().includes(q.toLowerCase()));
  const groupName = (g: string | null) => s.groups.find((x) => x.name === g)?.display_name ?? "–";
  return (
    <>
      <Crumbs items={[{ label: "Ontology", to: "/" }, { label: "Object types" }]} />
      <div className="spread" style={{ margin: "4px 0 14px" }}>
        <div>
          <h1 className="page-title">Object types {group && <span className="chip accent" style={{ verticalAlign: "middle" }}>{groupName(group)}</span>}</h1>
          <p className="page-sub">Every entity in the ontology, its backing dataset and how many objects it holds.</p>
        </div>
        <input className="text-input" placeholder="Filter…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="glass om-table">
        <table>
          <thead><tr><th>Object type</th><th>Group</th><th>Status</th><th>Sources</th><th className="r">Objects</th><th className="r">Properties</th><th className="r">Links</th><th>Updated</th></tr></thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.name} onClick={() => navigate(`/object-types/${t.name}`)}>
                <td><span className="row" style={{ gap: 10, flexWrap: "nowrap" }}><TypeIcon icon={t.icon} color={t.color} size={26} /><span><b>{displayName(t.name)}</b><br /><span className="faint mono" style={{ fontSize: 11 }}>{t.name}</span></span></span></td>
                <td className="muted">{groupName(t.group)}</td>
                <td><StatusChip t={t} /></td>
                <td>{t.sources.map((src) => <span key={src} className={`om-src ${src}`}>{SOURCE_LABEL[src] ?? src}</span>)}</td>
                <td className="r num">{t.count.toLocaleString()}</td>
                <td className="r num">{t.properties.length}</td>
                <td className="r num">{t.links.length}</td>
                <td className="faint">{ago(t.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

const StatusChip = ({ t }: { t: ObjectType }) =>
  t.is_dataset ? <span className="chip">Time series</span>
    : t.sources.includes("writeback") ? <span className="chip accent">Write-back</span>
      : t.optional ? <span className="chip">Optional source</span>
        : <span className="chip good">Active</span>;

/* ------------------------------------------------------------------ object type view */

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "properties", label: "Properties" },
  { key: "links", label: "Link types" },
  { key: "datasources", label: "Datasources" },
  { key: "actions", label: "Actions" },
  { key: "objects", label: "Objects" },
] as const;

export function ObjectTypeView() {
  const s = schemaOf(useOm());
  const { name = "", tab = "overview" } = useParams();
  const t = s.object_types.find((x) => x.name === name);
  if (!t) return <div className="error-box">Unknown object type {name}</div>;
  const actions = s.action_types.filter((a) => a.object_type === t.name);
  return <ObjectTypeContent key={t.name} t={t} s={s} tab={tab} actions={actions} />;
}

function ObjectTypeContent({t,s,tab,actions}: {t:ObjectType;s:OntologySchema;tab:string;actions:ActionType[]}) {
  const navigate=useNavigate();
  const [configure,setConfigure]=useState(false);
  return (
    <>
      <Crumbs items={[{ label: "Ontology", to: "/" }, { label: "Object types", to: "/object-types" }, { label: displayName(t.name) }]} />
      <header className="om-type-head">
        <TypeIcon icon={t.icon} color={t.color} size={52} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="row" style={{ gap: 10 }}>
            <h1 className="page-title" style={{ margin: 0 }}>{displayName(t.name)}</h1>
            <StatusChip t={t} />
          </div>
          <div className="faint mono" style={{ fontSize: 12, margin: "2px 0 6px" }}>API name: {t.name} · ontology."{t.name}"</div>
          <p className="muted" style={{ margin: 0, maxWidth: 900 }}>{t.description}</p>
        </div>
        <button className="btn" onClick={() => setConfigure(true)}>Configure type</button>
        <div className="om-head-stats">
          <Stat label={t.is_dataset ? "Rows" : "Objects"} value={t.count.toLocaleString()} />
          <Stat label="Properties" value={String(t.properties.length)} />
          <Stat label="Links" value={String(t.links.length)} />
        </div>
      </header>
      <nav className="om-tabs">
        {TABS.map((x) => (
          <button key={x.key} className={tab === x.key ? "on" : ""} onClick={() => navigate(`/object-types/${t.name}${x.key === "overview" ? "" : `/${x.key}`}`)}>
            {x.label}
            {x.key === "properties" && <span className="om-count">{t.properties.length}</span>}
            {x.key === "links" && <span className="om-count">{t.links.length}</span>}
            {x.key === "actions" && <span className="om-count">{actions.length}</span>}
          </button>
        ))}
      </nav>
      {configure && <MetadataEditor type={t} onClose={() => setConfigure(false)} />}
      {tab === "overview" && <TypeOverview t={t} s={s} />}
      {tab === "properties" && <PropertiesTable t={t} />}
      {tab === "links" && <TypeLinks t={t} s={s} />}
      {tab === "datasources" && <Datasources t={t} />}
      {tab === "actions" && <ActionsList actions={actions} s={s} empty={`No actions modify ${displayName(t.name)}. Use Objects to edit property values through isolated overrides. Experiment and Day note also have dedicated actions.`} />}
      {tab === "objects" && <div className="glass card"><ObjectsBrowser ot={t} schema={s.object_types} height={600} /></div>}
    </>
  );
}

function Meta({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="om-meta">
      {rows.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
    </dl>
  );
}

function TypeOverview({ t, s }: { t: ObjectType; s: OntologySchema }) {
  const navigate = useNavigate();
  return (
    <div className="grid">
      <section className="glass card span-4">
        <h3 className="card-title" style={{ marginBottom: 10 }}>Metadata</h3>
        <Meta rows={[
          ["Display name", displayName(t.name)],
          ["API name", <span className="mono">{t.name}</span>],
          ["Primary key", <span className="mono">{t.primary_key}</span>],
          ["Title property", <span className="mono">{t.title ?? "–"}</span>],
          ["Group", s.groups.find((g) => g.name === t.group)?.display_name ?? "–"],
          ["Backing dataset", <span className="mono">{t.backing_dataset}</span>],
          ["Sources", t.sources.map((x) => SOURCE_LABEL[x] ?? x).join(", ") || "–"],
          ["Last built", ago(t.updated_at)],
        ]} />
      </section>
      <section className="glass card span-8">
        <div className="spread" style={{ marginBottom: 8 }}>
          <h3 className="card-title">Neighbourhood</h3>
          <span className="faint" style={{ fontSize: 12 }}>Linked object types · click to navigate</span>
        </div>
        <OntologyGraph focus={t.name} height={300} />
      </section>
      <section className="glass card span-12">
        <div className="spread" style={{ marginBottom: 8 }}>
          <h3 className="card-title">Properties</h3>
          <button className="btn" onClick={() => navigate(`/object-types/${t.name}/properties`)}>All {t.properties.length}</button>
        </div>
        <PropertiesTable t={t} limit={8} bare />
      </section>
    </div>
  );
}

/** A property's values at a glance: top values for categoricals, range and median for numbers / dates. */
function ValueSummary({ type, prof }: { type: string; prof?: PropertyProfile }) {
  if (!prof) return <span className="faint">–</span>;
  if (prof.top?.length) {
    const total = prof.top.reduce((a, b) => a + b.n, 0);
    return (
      <span className="row" style={{ gap: 4 }}>
        {prof.top.slice(0, 4).map((v) => <span key={v.value} className="chip" title={`${v.n.toLocaleString()} objects`}>{v.value} <span className="faint">{Math.round((v.n / total) * 100)}%</span></span>)}
      </span>
    );
  }
  const short = (v: string | null) => (v == null ? "–" : type === "double" ? num(Number(v), Math.abs(Number(v)) < 10 ? 2 : 1) : type === "timestamp" ? v.slice(0, 16).replace("T", " ") : v);
  if (prof.min == null && prof.max == null) return <span className="faint">all empty</span>;
  return (
    <span className="mono" style={{ fontSize: 11.5 }}>
      {short(prof.min)} → {short(prof.max)}
      {(type === "double" || type === "integer") && prof.q50 != null && <span className="faint"> · median {short(prof.q50)}</span>}
    </span>
  );
}

function PropertiesTable({ t, limit, bare = false }: { t: ObjectType; limit?: number; bare?: boolean }) {
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const { data: prof } = useProfile(t.name);
  const props = t.properties.filter((p) => `${p.name} ${p.description}`.toLowerCase().includes(q.toLowerCase())).slice(0, limit);
  const fks = new Set(t.links.filter((l) => l.direction === "to_one").map((l) => l.foreign_key));
  const table = (
    <div className={bare ? "om-table bare" : "glass om-table"}>
      <table>
        <thead><tr><th>Display name</th><th>API name</th><th>Base type</th><th>Keys</th><th className="r">Null</th><th className="r">Distinct</th><th>Values</th><th>Description</th></tr></thead>
        <tbody>
          {props.map((p) => (
            <tr key={p.name} onClick={() => setEditing(p.name)}>
              <td><b>{p.display_name || propDisplay(p.name)}</b></td>
              <td className="mono faint">{p.name}</td>
              <td><span className={`om-type-badge ${p.type}`}>{TYPE_BADGE[p.type] ?? p.type}</span></td>
              <td>
                {p.name === t.primary_key && <span className="chip accent">Primary key</span>}
                {p.name === t.title && <span className="chip">Title</span>}
                {fks.has(p.name) && <span className="chip">Foreign key</span>}
              </td>
              <td className="r num faint">{prof?.properties[p.name]?.null_pct == null ? "–" : `${num(prof.properties[p.name].null_pct! * 100, prof.properties[p.name].null_pct! > 0 && prof.properties[p.name].null_pct! < 0.01 ? 1 : 0)}%`}</td>
              <td className="r num faint">{prof?.properties[p.name]?.distinct?.toLocaleString() ?? "–"}</td>
              <td className="om-values"><ValueSummary type={p.type} prof={prof?.properties[p.name]} /></td>
              <td className="muted">{p.description || <span className="faint">–</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  const editor = editing ? <MetadataEditor type={t} property={t.properties.find(p => p.name === editing)!} onClose={() => setEditing(null)} /> : null;
  if (bare) return <>{table}{editor}</>;
  return (
    <>
      <div className="row" style={{ marginBottom: 10 }}>
        <input className="text-input" placeholder="Filter properties…" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="faint" style={{ fontSize: 12 }}>{props.length} of {t.properties.length}</span>
      </div>
      {table}
      {editor}
    </>
  );
}

function TypeLinks({ t, s }: { t: ObjectType; s: OntologySchema }) {
  const navigate = useNavigate();
  const typeOf = (n: string) => s.object_types.find((x) => x.name === n)!;
  return (
    <div className="glass om-table">
      <table>
        <thead><tr><th>Link type</th><th>Linked object type</th><th>Cardinality</th><th>Join</th></tr></thead>
        <tbody>
          {t.links.map((l) => {
            const other = typeOf(l.target);
            return (
              <tr key={`${l.name}-${l.direction}`} onClick={() => navigate(`/object-types/${other.name}`)}>
                <td className="mono">{l.name}</td>
                <td><span className="row" style={{ gap: 8, flexWrap: "nowrap" }}><TypeIcon icon={other.icon} color={other.color} size={22} />{displayName(other.name)}</span></td>
                <td>{l.direction === "to_one" ? <span className="chip">Many → one</span> : <span className="chip accent">One → many</span>}</td>
                <td className="mono faint">{l.many}.{l.foreign_key} = {l.one}.{typeOf(l.one).primary_key}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Datasources({ t }: { t: ObjectType }) {
  const steps = [...t.lineage, t.backing_dataset];
  const layer = (x: string) => x.split("/")[0];
  return (
    <div className="glass card">
      <h3 className="card-title">Lineage</h3>
      <p className="card-sub" style={{ marginBottom: 16 }}>
        How {displayName(t.name)} is built: immutable landing batches → raw (strings + lineage) → transformed (typed, UTC-corrected) → clean (this type's backing dataset) → the ontology view.
        Validation fails the build if the dataset drifts from the declared properties.
      </p>
      <div className="lineage">
        {steps.map((x, i) => (
          <div key={x + i} className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
            <div className={`lineage-node ${layer(x)}`}>
              <span className="faint" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".06em" }}>{x === t.backing_dataset ? "backing dataset" : layer(x)}</span>
              <span className="mono">{x.split("/").slice(1).join("/") || x}</span>
            </div>
            <span className="faint">→</span>
          </div>
        ))}
        <div className="lineage-node object">
          <span className="faint" style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".06em" }}>object type</span>
          <span className="row" style={{ gap: 6 }}><TypeIcon icon={t.icon} color={t.color} size={18} />{t.name}</span>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ link types / action types */

export function LinkTypesPage() {
  const s = schemaOf(useOm());
  const navigate = useNavigate();
  const typeOf = (n: string) => s.object_types.find((x) => x.name === n)!;
  return (
    <>
      <Crumbs items={[{ label: "Ontology", to: "/" }, { label: "Link types" }]} />
      <h1 className="page-title" style={{ margin: "4px 0 2px" }}>Link types</h1>
      <p className="page-sub" style={{ marginBottom: 14 }}>Relationships between object types, each declared by a foreign-key property and validated on every build (no dangling links).</p>
      <div className="glass om-table">
        <table>
          <thead><tr><th>API name</th><th>Many side</th><th /><th>One side</th><th>Foreign key</th></tr></thead>
          <tbody>
            {s.link_types.map((l) => {
              const a = typeOf(l.many), b = typeOf(l.one);
              return (
                <tr key={l.name} onClick={() => navigate(`/object-types/${a.name}/links`)}>
                  <td className="mono">{l.name}</td>
                  <td><span className="row" style={{ gap: 8, flexWrap: "nowrap" }}><TypeIcon icon={a.icon} color={a.color} size={22} />{displayName(a.name)}</span></td>
                  <td className="faint">→</td>
                  <td><span className="row" style={{ gap: 8, flexWrap: "nowrap" }}><TypeIcon icon={b.icon} color={b.color} size={22} />{displayName(b.name)}</span></td>
                  <td className="mono faint">{l.foreign_key}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ActionsList({ actions, s, empty }: { actions: ActionType[]; s: OntologySchema; empty: string }) {
  const [running, setRunning] = useState<string | null>(null);
  if (!actions.length) return <div className="glass card muted">{empty}</div>;
  return (
    <div className="om-cards">
      {actions.map((a) => {
        const t = s.object_types.find((x) => x.name === a.object_type)!;
        return (
          <div key={a.name} className="glass om-card static">
            <div className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
              <TypeIcon icon="bolt" color="#f59e0b" size={34} />
              <div>
                <div className="om-card-title">{a.display_name}</div>
                <div className="faint mono" style={{ fontSize: 11 }}>{a.name} · {a.kind} {a.object_type}</div>
              </div>
            </div>
            <p className="om-card-desc">{a.description}</p>
            <div className="om-params">
              {a.parameters.map((p) => (
                <span key={p.name} className="om-param" title={p.enum.length ? `one of: ${p.enum.join(", ")}` : undefined}>
                  <span className="mono">{p.name}</span><span className={`om-type-badge ${p.type}`}>{TYPE_BADGE[p.type]}</span>{p.required && <span className="req">*</span>}
                </span>
              ))}
            </div>
            <div className="spread" style={{ marginTop: 10 }}>
              <span className="row faint" style={{ gap: 6, fontSize: 12 }}><TypeIcon icon={t.icon} color={t.color} size={18} />{displayName(t.name)}</span>
              {a.kind === "create" && <button className="btn primary" onClick={() => setRunning(a.name)}>Run</button>}
            </div>
          </div>
        );
      })}
      {running && <ActionDrawer name={running} onClose={() => setRunning(null)} hidden={["insight_id"]} />}
    </div>
  );
}

export function ActionTypesPage() {
  const s = schemaOf(useOm());
  return (
    <>
      <Crumbs items={[{ label: "Ontology", to: "/" }, { label: "Action types" }]} />
      <h1 className="page-title" style={{ margin: "4px 0 2px" }}>Action types</h1>
      <p className="page-sub" style={{ marginBottom: 14 }}>Typed actions create experiments and notes in the write-back store. Object value overrides are managed separately from the Objects tab.</p>
      <ActionsList actions={s.action_types} s={s} empty="No action types declared." />
    </>
  );
}
