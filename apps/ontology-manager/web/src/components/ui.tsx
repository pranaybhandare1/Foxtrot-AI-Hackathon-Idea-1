/** Small presentational building blocks: cards, KPIs, controls, loading and error states. */

import type { ReactNode } from "react";
import { Icons } from "./Icons";

export function Card({ title, sub, actions, children, className = "", flush = false }: {
  title?: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
}) {
  return (
    <section className={`glass card ${flush ? "flush" : ""} ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h3 className="card-title">{title}</h3>}
            {sub && <p className="card-sub">{sub}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function PageHead({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page-title">{title}</h1>
        {sub && <p className="page-sub">{sub}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

/** A metric tile. `delta` is current - previous; `better` says which direction is good. */
export function Kpi({ label, value, unit, delta, deltaFormat, better, foot, color }: {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  delta?: number | null;
  deltaFormat?: (d: number) => string;
  better?: "up" | "down";
  foot?: ReactNode;
  color?: string;
}) {
  let deltaEl: ReactNode = null;
  if (delta != null && !Number.isNaN(delta) && deltaFormat) {
    const flat = Math.abs(delta) < 1e-9;
    const good = better ? (better === "up" ? delta > 0 : delta < 0) : null;
    const cls = flat || good == null ? "flat" : good ? "good" : "bad";
    deltaEl = (
      <span className={`delta ${cls}`}>
        {!flat && (delta > 0 ? <Icons.arrowUp /> : <Icons.arrowDown />)} {deltaFormat(delta)}
      </span>
    );
  }
  return (
    <div className="glass kpi">
      <div className="kpi-label">
        {color && <span className="dot" style={{ background: color }} />}
        {label}
      </div>
      <div className="kpi-value">
        {value}
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      {(deltaEl || foot) && (
        <div className="kpi-foot">
          {deltaEl}
          {deltaEl && foot ? <span>·</span> : null}
          {foot}
        </div>
      )}
    </div>
  );
}

export function Segmented<T extends string>({ options, value, onChange }: {
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="segmented" role="tablist">
      {options.map((o) => (
        <button key={o.value} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)}
          role="tab" aria-selected={o.value === value}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
      {label}
    </label>
  );
}

export function Skeleton({ height = 240 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} />;
}

export function ErrorBox({ error }: { error: unknown }) {
  return <div className="error-box">Could not load data: {error instanceof Error ? error.message : String(error)}</div>;
}

/** Render children once data is ready; skeleton while loading; error box on failure. */
export function Loader<T>({ query, height, children }: {
  query: { data: T | undefined; isLoading: boolean; error: unknown };
  height?: number;
  children: (data: T) => ReactNode;
}) {
  if (query.error) return <ErrorBox error={query.error} />;
  if (query.isLoading || query.data === undefined) return <Skeleton height={height} />;
  return <>{children(query.data)}</>;
}

export function Legend({ items }: { items: { label: string; color: string; shape?: "dot" | "line" }[] }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span key={i.label}>
          <span className="dot" style={{ background: i.color, borderRadius: i.shape === "line" ? 2 : undefined, height: i.shape === "line" ? 3 : 8, width: i.shape === "line" ? 14 : 8 }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}
