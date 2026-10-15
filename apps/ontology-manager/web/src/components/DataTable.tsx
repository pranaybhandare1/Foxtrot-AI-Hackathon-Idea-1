/**
 * Virtualized, sortable table with a sticky frosted header and optional sticky first column.
 * Renders only visible rows, so tens of thousands of rows scroll smoothly.
 */

import { useVirtualizer } from "@tanstack/react-virtual";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { Icons } from "./Icons";

export type Column<T> = {
  key: string;
  header: ReactNode;
  width?: number;
  align?: "left" | "right";
  render?: (row: T) => ReactNode;
  value?: (row: T) => unknown; // for sorting / default rendering
  sortable?: boolean;
};

type Props<T> = {
  columns: Column<T>[];
  rows: T[];
  height?: number | string;
  rowHeight?: number;
  onRowClick?: (row: T) => void;
  initialSort?: { key: string; desc: boolean };
  stickyFirst?: boolean;
  empty?: ReactNode;
  rowKey?: (row: T, index: number) => string;
};

const cellValue = <T,>(c: Column<T>, row: T) => (c.value ? c.value(row) : (row as Record<string, unknown>)[c.key]);

function compare(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "boolean" && typeof b === "boolean") return Number(a) - Number(b);
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

function defaultRender(v: unknown): ReactNode {
  if (v == null) return <span className="faint">–</span>;
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  const s = String(v);
  return /^\d{4}-\d{2}-\d{2}T/.test(s) ? s.replace("T", " ").slice(0, 16) : s;
}

export function DataTable<T>({
  columns, rows, height = 420, rowHeight = 36, onRowClick, initialSort, stickyFirst = false, empty, rowKey,
}: Props<T>) {
  const [sort, setSort] = useState(initialSort ?? null);
  const scroller = useRef<HTMLDivElement>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const out = [...rows].sort((a, b) => compare(cellValue(col, a), cellValue(col, b)));
    return sort.desc ? out.reverse() : out;
  }, [rows, sort, columns]);

  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: sorted.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => rowHeight,
    overscan: 12,
  });

  // each column keeps its width as a minimum and shares any extra space in proportion to it
  const template = columns.map((c) => `minmax(${c.width ?? 110}px, ${c.width ?? 110}fr)`).join(" ");
  const minWidth = columns.reduce((s, c) => s + (c.width ?? 110), 0);

  const toggleSort = (c: Column<T>) => {
    if (c.sortable === false) return;
    setSort((s) => (s?.key === c.key ? { key: c.key, desc: !s.desc } : { key: c.key, desc: true }));
  };

  return (
    <div className="table-wrap" ref={scroller} style={{ height }}>
      <div className="dt" style={{ minWidth }}>
        <div className="dt-head" style={{ gridTemplateColumns: template }}>
          {columns.map((c, i) => (
            <div key={c.key} className={`dt-th ${c.align === "right" ? "right" : ""} ${stickyFirst && i === 0 ? "sticky-col" : ""}`}
              onClick={() => toggleSort(c)} title={typeof c.header === "string" ? c.header : undefined}>
              {c.header}
              {sort?.key === c.key && (sort.desc ? <Icons.arrowDown /> : <Icons.arrowUp />)}
            </div>
          ))}
        </div>
        {sorted.length === 0 ? (
          <div className="dt-empty">{empty ?? "No rows match the current filters."}</div>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((v) => {
              const row = sorted[v.index];
              return (
                <div key={rowKey ? rowKey(row, v.index) : v.key} className={`dt-row ${onRowClick ? "clickable" : ""}`}
                  style={{ gridTemplateColumns: template, height: rowHeight, transform: `translateY(${v.start}px)` }}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}>
                  {columns.map((c, i) => (
                    <div key={c.key} className={`dt-td ${c.align === "right" ? "right" : ""} ${stickyFirst && i === 0 ? "sticky-col" : ""}`}>
                      {c.render ? c.render(row) : <span>{defaultRender(cellValue(c, row))}</span>}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
