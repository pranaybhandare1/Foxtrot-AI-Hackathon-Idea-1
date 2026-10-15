/** Object browsing: the objects table (search, filters, virtualized) and a drawer that follows links object to object. */

import { Fragment, useEffect, useMemo, useState } from "react";
import { useObject, useObjects } from "../api/client";
import type { ObjectType } from "../api/types";
import { DataTable, type Column } from "../components/DataTable";
import { Drawer } from "../components/Drawer";
import { Icons } from "../components/Icons";
import { Loader } from "../components/ui";
import { RecordEditor } from "./ManagerPages";
import { num } from "../lib/format";

type Row = Record<string, unknown>;
const OPS = [
  { value: "eq", label: "=" }, { value: "ne", label: "≠" }, { value: "gt", label: ">" }, { value: "gte", label: "≥" },
  { value: "lt", label: "<" }, { value: "lte", label: "≤" }, { value: "contains", label: "contains" },
  { value: "isnull", label: "is empty" }, { value: "notnull", label: "is set" },
];

export const fmt = (v: unknown) => {
  if (v == null) return "–";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : num(v, 3);
  if (typeof v === "boolean") return v ? "true" : "false";
  const s = String(v);
  return /^\d{4}-\d{2}-\d{2}T/.test(s) ? s.replace("T", " ").slice(0, 19) : s;
};

export function columnsFor(ot: ObjectType): Column<Row>[] {
  const order = [ot.primary_key, ...(ot.title && ot.title !== ot.primary_key ? [ot.title] : []), ...ot.properties.map((p) => p.name)];
  const seen = new Set<string>();
  return order.filter((n) => !seen.has(n) && seen.add(n)).map((name) => {
    const p = ot.properties.find((x) => x.name === name)!;
    const numeric = p.type === "double" || p.type === "integer";
    return { key: name, header: name, width: p.type === "timestamp" ? 170 : numeric ? 120 : p.type === "boolean" ? 96 : 160, align: numeric ? "right" : "left",
      render: (r: Row) => <span title={p.description}>{fmt(r[name])}</span> };
  });
}

type Crumb = { type: string; pk: string };

export function ObjectDrawer({ start, schema, onClose }: { start: Crumb; schema: ObjectType[]; onClose: () => void }) {
  const [editing, setEditing] = useState(false);
  const [trail, setTrail] = useState<Crumb[]>([start]);
  const cur = trail[trail.length - 1];
  const q = useObject(cur.type, cur.pk);
  const typeOf = (name: string) => schema.find((t) => t.name === name)!;
  const open = (type: string, pk: unknown) => setTrail((t) => [...t, { type, pk: String(pk) }]);
  return (
    <Drawer title={<span className="row" style={{ gap: 8 }}><span className="chip accent">{cur.type}</span>{cur.pk}</span>}
      sub={<div className="breadcrumbs">{trail.map((c, i) => (
        <span key={i} className="row" style={{ gap: 6 }}>
          {i > 0 && <span>›</span>}
          {i < trail.length - 1 ? <button onClick={() => setTrail(trail.slice(0, i + 1))}>{c.type}</button> : <span>{c.type}</span>}
        </span>))}</div>}
      onClose={onClose}>
      <Loader query={q} height={300}>
        {(d) => {
          const day = cur.type === "Day" ? undefined : (d.object.date_local as string | undefined);
          return (
            <>
              {day && <button className="btn primary" style={{ marginBottom: 14 }} onClick={() => open("Day", day)}>Open Day {day} <Icons.external /></button>}
              <div className="object-edit-toolbar"><span className="muted">Ontology object · effective values</span><button className="btn primary" onClick={() => setEditing(true)}>Edit values</button></div>
              {editing ? <RecordEditor key={`${cur.type}:${cur.pk}`} type={typeOf(cur.type)} pk={cur.pk} onClose={() => setEditing(false)} /> : <dl className="kv">
                {typeOf(d.type).properties.map((p) => (
                  <Fragment key={p.name}><dt title={p.description}>{p.name}</dt><dd>{fmt(d.object[p.name])}</dd></Fragment>
                ))}
              </dl>}
              {d.links.map((l) => {
                const target = typeOf(l.target);
                return (
                  <div key={l.link} className="link-block">
                    <div className="link-title">
                      <span className="row" style={{ gap: 8 }}><Icons.explorer /> {l.link} <span className="faint">→ {l.target}</span></span>
                      <span className="chip">{l.total.toLocaleString()}{l.rows.length < l.total ? ` · showing ${l.rows.length}` : ""}</span>
                    </div>
                    {l.rows.length > 0 ? (
                      <DataTable columns={columnsFor(target).slice(0, 8)} rows={l.rows} height={l.cardinality === "one" ? 80 : 240} rowHeight={32}
                        onRowClick={(r) => open(l.target, r[target.primary_key])} />
                    ) : (
                      <div className="faint" style={{ fontSize: 12 }}>No linked objects</div>
                    )}
                  </div>
                );
              })}
            </>
          );
        }}
      </Loader>
    </Drawer>
  );
}

/** Objects of one type: search, property filters, a virtualized table, and a drawer that follows links. */
export function ObjectsBrowser({ ot, schema, height = 560 }: { ot: ObjectType; schema: ObjectType[]; height?: number }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [filters, setFilters] = useState<string[]>([]);
  const [draft, setDraft] = useState({ col: "", op: "gte", value: "" });
  const [open, setOpen] = useState<Crumb | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  const objects = useObjects(ot.name, { q: debounced || undefined, filter: filters });
  const columns = useMemo(() => columnsFor(ot), [ot]);

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row">
        <div className="row" style={{ gap: 6, flex: "1 1 220px" }}>
          <Icons.search />
          <input className="text-input" style={{ flex: 1 }} placeholder={`Search ${ot.name} text properties…`} value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="select" value={draft.col} onChange={(e) => setDraft({ ...draft, col: e.target.value })}>
          <option value="">Property…</option>
          {ot.properties.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
        </select>
        <select className="select" value={draft.op} onChange={(e) => setDraft({ ...draft, op: e.target.value })}>
          {OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {!["isnull", "notnull"].includes(draft.op) && (
          <input className="text-input" style={{ width: 130 }} placeholder="value" value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} />
        )}
        <button className="btn" disabled={!draft.col} onClick={() => { setFilters((f) => [...f, `${draft.col}:${draft.op}${["isnull", "notnull"].includes(draft.op) ? "" : `:${draft.value}`}`]); setDraft({ ...draft, value: "" }); }}>Add filter</button>
      </div>
      {filters.length > 0 && (
        <div className="row">
          {filters.map((f, i) => (
            <span key={f} className="chip accent" style={{ cursor: "pointer" }} onClick={() => setFilters(filters.filter((_, j) => j !== i))}>
              {f.replace(/:(eq|ne|gt|gte|lt|lte|contains|isnull|notnull):?/, (_m, op) => ` ${OPS.find((o) => o.value === op)?.label} `)} ✕
            </span>
          ))}
        </div>
      )}
      <div className="table-meta">
        <span className="muted" style={{ fontSize: 12 }}>
          {objects.data ? `${objects.data.total.toLocaleString()} objects${objects.data.total > objects.data.rows.length ? ` · first ${objects.data.rows.length.toLocaleString()} loaded` : ""}` : "Loading…"}
        </span>
        <span className="faint" style={{ fontSize: 12 }}>Hover a value for the property description · click a row to open the object</span>
      </div>
      {objects.error ? <div className="error-box">{String(objects.error)}</div> : (
        <DataTable key={ot.name} columns={columns} rows={objects.data?.rows ?? []} height={height} stickyFirst
          onRowClick={(r) => setOpen({ type: ot.name, pk: String(r[ot.primary_key]) })} />
      )}
      {open && <ObjectDrawer key={`${open.type}:${open.pk}`} start={open} schema={schema} onClose={() => setOpen(null)} />}
    </div>
  );
}
