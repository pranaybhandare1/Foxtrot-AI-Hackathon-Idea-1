/**
 * A form generated from an ontology action type (Foundry "action form"): one field per typed parameter,
 * enums as selects, required fields enforced. Submits through POST /api/actions/{name}.
 */

import { useState, type ReactNode } from "react";
import { useApplyAction, useOntology } from "../api/client";
import type { ActionType, MetricSpec } from "../api/types";
import { Drawer } from "./Drawer";
import { TypeIcon } from "./TypeIcon";

type Values = Record<string, string>;

const LABELS: Record<string, string> = {
  title: "Title", hypothesis: "Hypothesis", insight_id: "From insight", metric: "Tracked metric", better: "Better is",
  start_date: "Start", end_date: "End", status: "Status", notes: "Notes", date_local: "Day", text: "Note", tags: "Tags",
  experiment_id: "Experiment",
};

export function ActionForm({ action, initial = {}, metrics, onDone, hidden = [] }: {
  action: ActionType;
  initial?: Values;
  metrics?: Record<string, MetricSpec>;
  onDone?: (pk: string) => void;
  hidden?: string[];
}) {
  const [values, setValues] = useState<Values>(initial);
  const apply = useApplyAction();
  const missing = action.parameters.filter((p) => p.required && !values[p.name]);
  const set = (k: string, v: string) => setValues((s) => ({ ...s, [k]: v }));

  const field = (name: string, type: string, enumValues: string[]): ReactNode => {
    const v = values[name] ?? "";
    if (enumValues.length)
      return (
        <select className="select" value={v} onChange={(e) => set(name, e.target.value)}>
          <option value="">Choose…</option>
          {enumValues.map((o) => <option key={o} value={o}>{name === "metric" && metrics?.[o] ? metrics[o].label : o}</option>)}
        </select>
      );
    if (type === "date") return <input className="date-input" type="date" value={v} onChange={(e) => set(name, e.target.value)} />;
    if (name === "text" || name === "hypothesis" || name === "notes")
      return <textarea className="text-input" rows={3} value={v} onChange={(e) => set(name, e.target.value)} />;
    return <input className="text-input" value={v} onChange={(e) => set(name, e.target.value)} />;
  };

  return (
    <form className="action-form" onSubmit={(e) => {
      e.preventDefault();
      const params = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
      apply.mutate({ name: action.name, params }, { onSuccess: (r) => onDone?.(r.primary_key) });
    }}>
      {action.parameters.filter((p) => !hidden.includes(p.name)).map((p) => (
        <label key={p.name} className="action-field">
          <span className="action-label">
            {LABELS[p.name] ?? p.name}
            {p.required && <span className="req">*</span>}
            <span className="faint mono">{p.type}</span>
          </span>
          {field(p.name, p.type, p.enum)}
          {p.name === "metric" && values.metric && metrics?.[values.metric] && (
            <span className="faint" style={{ fontSize: 11.5 }}>{metrics[values.metric].better === "higher" ? "Higher" : "Lower"} is better by default</span>
          )}
        </label>
      ))}
      {apply.error && <div className="error-box">{String(apply.error.message)}</div>}
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button className="btn primary" type="submit" disabled={missing.length > 0 || apply.isPending}>
          {apply.isPending ? "Saving…" : action.display_name}
        </button>
      </div>
    </form>
  );
}

/** The form in a side drawer, looked up by action name from the ontology. */
export function ActionDrawer({ name, initial, metrics, onClose, hidden }: {
  name: string;
  initial?: Values;
  metrics?: Record<string, MetricSpec>;
  onClose: () => void;
  hidden?: string[];
}) {
  const schema = useOntology();
  const action = schema.data?.action_types.find((a) => a.name === name);
  const target = schema.data?.object_types.find((t) => t.name === action?.object_type);
  if (!action) return null;
  return (
    <Drawer onClose={onClose}
      title={<span className="row" style={{ gap: 10 }}>{target && <TypeIcon icon={target.icon} color={target.color} size={26} />}{action.display_name}</span>}
      sub={<>{action.description} <span className="faint mono">· {action.kind} {action.object_type}</span></>}>
      <ActionForm action={action} initial={initial} metrics={metrics} onDone={onClose} hidden={hidden} />
    </Drawer>
  );
}
