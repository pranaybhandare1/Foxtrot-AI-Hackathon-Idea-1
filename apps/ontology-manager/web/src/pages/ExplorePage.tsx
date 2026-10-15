/**
 * Explore & visualize: read-only SQL over the ontology (tables are named after object types) with an instant
 * chart builder, for prototyping the visuals a workflow or agent answer would need.
 */

import { useEffect, useMemo, useState } from "react";
import { useOntology, useSql } from "../api/client";
import type { SqlResult } from "../api/types";
import { DataTable, type Column } from "../components/DataTable";
import { EChart } from "../components/EChart";
import { TypeIcon } from "../components/TypeIcon";
import { Segmented } from "../components/ui";
import { axisCommon, tooltip } from "../lib/chartTheme";
import { num } from "../lib/format";
import { fmt } from "./ObjectsBrowser";

const EXAMPLES: { title: string; sql: string }[] = [
  {
    title: "Time in range by month",
    sql: `SELECT date_trunc('month', date_local) AS month,
       round(avg(tir) * 100, 1) AS tir_pct,
       round(avg(mean_sg_mgdl)) AS mean_glucose,
       round(avg(tdd_u), 1) AS insulin_u
FROM "Day" WHERE is_valid_cgm_day
GROUP BY 1 ORDER BY 1`,
  },
  {
    title: "Sleep the night before vs. next-day TIR",
    sql: `SELECT round(o.total_sleep_min / 60) AS sleep_hours,
       count(*) AS days,
       round(avg(d.tir) * 100, 1) AS tir_pct
FROM "Day" d JOIN "OuraDay" o USING (date_local)
WHERE d.is_valid_cgm_day AND o.total_sleep_min IS NOT NULL
GROUP BY 1 ORDER BY 1`,
  },
  {
    title: "Bedtime glucose vs. overnight TIR",
    sql: `SELECT sg_at_bedtime_mgdl, round(tir * 100) AS overnight_tir_pct, date_local
FROM "SleepSession"
WHERE sleep_type = 'long_sleep' AND cgm_coverage >= 0.7 AND sg_at_bedtime_mgdl IS NOT NULL`,
  },
  {
    title: "Meal rise by slot and pre-bolus timing",
    sql: `SELECT meal_slot,
       CASE WHEN trend_at_meal_mgdl_per_min > 0.5 THEN 'already rising' ELSE 'before the rise' END AS bolus_timing,
       count(*) AS meals, round(median(rise_to_peak_mgdl)) AS median_rise
FROM "Meal" WHERE cgm_coverage_window >= 0.7
GROUP BY ALL ORDER BY meal_slot, bolus_timing`,
  },
  {
    title: "Average glucose by hour of day",
    sql: `SELECT hour(bin_start_local) AS hour,
       round(avg(sg_mgdl)) AS mean_glucose,
       round(avg((sg_mgdl > 180)::INT) * 100) AS pct_above_180,
       round(avg((sg_mgdl < 70)::INT) * 100, 1) AS pct_below_70
FROM "Glucose5Min" WHERE has_data
GROUP BY 1 ORDER BY 1`,
  },
  {
    title: "Workouts and lows within 12 h",
    sql: `SELECT activity, count(*) AS workouts, round(avg(duration_min)) AS avg_min,
       round(avg(low_within_12h::INT) * 100) AS pct_followed_by_low
FROM "Workout" WHERE duration_min >= 20
GROUP BY 1 ORDER BY workouts DESC`,
  },
  {
    title: "Readiness vs. insulin needs",
    sql: `SELECT o.readiness_score, d.tdd_u, d.date_local
FROM "Day" d JOIN "OuraDay" o USING (date_local)
WHERE d.is_valid_cgm_day AND NOT d.is_partial_day AND o.readiness_score IS NOT NULL`,
  },
];

const KEY = "om.explore.sql";
const loadSql = () => {
  try {
    return localStorage.getItem(KEY) ?? EXAMPLES[0].sql;
  } catch {
    return EXAMPLES[0].sql;
  }
};
const isNumeric = (t: string) => /Int|Float|Decimal/.test(t);
const isTime = (t: string) => /Date|Datetime/.test(t);
type Chart = "bar" | "line" | "scatter" | "table";

function guess(r: SqlResult): { x: string; y: string[]; chart: Chart } {
  const cols = r.columns;
  const timeCol = cols.find((c) => isTime(c.type));
  const firstNum = cols.findIndex((c) => isNumeric(c.type));
  const x = timeCol?.name ?? (firstNum > 0 ? cols[0].name : cols[0]?.name ?? "");
  const nums = cols.filter((c) => isNumeric(c.type) && c.name !== x).map((c) => c.name);
  const xNumeric = isNumeric(cols.find((c) => c.name === x)?.type ?? "");
  const chart: Chart = !nums.length ? "table" : timeCol ? "line" : xNumeric && r.rows.length > 40 ? "scatter" : "bar";
  return { x, y: nums.slice(0, chart === "scatter" ? 1 : 3), chart };
}

export function ExplorePage() {
  const schema = useOntology();
  const run = useSql();
  const [sql, setSql] = useState(loadSql);
  const [chart, setChart] = useState<Chart>("bar");
  const [x, setX] = useState("");
  const [y, setY] = useState<string[]>([]);
  const result = run.data;

  useEffect(() => {
    try {
      localStorage.setItem(KEY, sql);
    } catch {
      /* private mode */
    }
  }, [sql]);

  const execute = (text = sql) =>
    run.mutate(text, {
      onSuccess: (r) => {
        const g = guess(r);
        setX(g.x);
        setY(g.y);
        setChart(g.chart);
      },
    });

  const columns = useMemo<Column<Record<string, unknown>>[]>(
    () => (result?.columns ?? []).map((c) => ({ key: c.name, header: c.name, width: isTime(c.type) ? 170 : 140, align: isNumeric(c.type) ? "right" : "left", render: (r) => <span>{fmt(r[c.name])}</span> })),
    [result],
  );
  const numericCols = (result?.columns ?? []).filter((c) => isNumeric(c.type)).map((c) => c.name);

  return (
    <>
      <div className="om-crumbs">Ideate / Explore & visualize</div>
      <h1 className="page-title" style={{ margin: "4px 0 2px" }}>Explore & visualize</h1>
      <p className="page-sub" style={{ marginBottom: 14 }}>
        Read-only SQL (DuckDB) over the ontology: every object type is a table, e.g. <code>"Day"</code>, <code>"Meal"</code>. Run with ⌘/Ctrl + Enter; the chart picks itself, then tweak it.
      </p>
      <div className="explore">
        <aside className="glass card explore-side">
          <h3 className="card-title" style={{ marginBottom: 8 }}>Starter questions</h3>
          <div className="type-list">
            {EXAMPLES.map((e) => (
              <div key={e.title} className="type-item" onClick={() => { setSql(e.sql); execute(e.sql); }}>{e.title}</div>
            ))}
          </div>
          <h3 className="card-title" style={{ margin: "16px 0 8px" }}>Tables</h3>
          <div className="row" style={{ gap: 6 }}>
            {schema.data?.object_types.map((t) => (
              <button key={t.name} className="chip" style={{ cursor: "pointer" }} title={t.description} onClick={() => setSql((s) => `${s}${s.endsWith(" ") || !s ? "" : " "}"${t.name}"`)}>
                <TypeIcon icon={t.icon} color={t.color} size={16} />{t.name}
              </button>
            ))}
          </div>
        </aside>
        <div className="stack" style={{ gap: 14, minWidth: 0 }}>
          <div className="glass card">
            <textarea className="sql-editor" spellCheck={false} value={sql} onChange={(e) => setSql(e.target.value)}
              onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); execute(); } }} />
            <div className="spread" style={{ marginTop: 10 }}>
              <span className="faint" style={{ fontSize: 12 }}>
                {run.isPending ? "Running…" : result ? `${result.rows.length.toLocaleString()} rows${result.truncated ? " (truncated)" : ""}` : "SELECT only · max 5,000 rows shown"}
              </span>
              <button className="btn primary" onClick={() => execute()} disabled={run.isPending}>Run</button>
            </div>
            {run.error && <div className="error-box" style={{ marginTop: 10 }}>{run.error.message}</div>}
          </div>
          {result && (
            <>
              <div className="glass card">
                <div className="row" style={{ marginBottom: 10 }}>
                  <Segmented value={chart} onChange={setChart} options={[{ value: "bar", label: "Bar" }, { value: "line", label: "Line" }, { value: "scatter", label: "Scatter" }, { value: "table", label: "Table only" }]} />
                  {chart !== "table" && (
                    <>
                      <label className="row faint" style={{ gap: 6, fontSize: 12 }}>x
                        <select className="select" value={x} onChange={(e) => setX(e.target.value)}>{result.columns.map((c) => <option key={c.name}>{c.name}</option>)}</select>
                      </label>
                      <span className="faint" style={{ fontSize: 12 }}>y</span>
                      {numericCols.filter((c) => c !== x).map((c) => (
                        <button key={c} className={`chip ${y.includes(c) ? "accent" : ""}`} style={{ cursor: "pointer" }}
                          onClick={() => setY((cur) => (cur.includes(c) ? cur.filter((v) => v !== c) : [...cur, c]))}>{c}</button>
                      ))}
                    </>
                  )}
                </div>
                {chart !== "table" && y.length > 0 ? (
                  <EChart height={340} deps={[result, chart, x, y]}
                    build={(p) => {
                      const xType = result.columns.find((c) => c.name === x)?.type ?? "";
                      const valueX = chart === "scatter" || (isNumeric(xType) && chart === "line");
                      const palette = [p.accent, "#a78bfa", "#34d399", "#f59e0b", "#f472b6"];
                      return {
                        tooltip: tooltip(p, { trigger: chart === "scatter" ? "item" : "axis", valueFormatter: (v: number) => num(v, 2) }),
                        legend: { top: 0, textStyle: { color: p.muted, fontSize: 11 } },
                        grid: { left: 56, right: 20, top: 30, bottom: 36 },
                        xAxis: valueX
                          ? { type: "value", scale: true, name: x, nameLocation: "middle", nameGap: 24, nameTextStyle: { color: p.muted }, ...axisCommon(p) }
                          : { type: "category", data: result.rows.map((r) => fmt(r[x])), ...axisCommon(p), axisLabel: { color: p.faint, fontSize: 10.5 } },
                        yAxis: { type: "value", scale: chart !== "bar", ...axisCommon(p) },
                        dataZoom: result.rows.length > 60 ? [{ type: "inside" }] : [],
                        series: y.map((col, i) => ({
                          name: col,
                          type: chart,
                          smooth: chart === "line",
                          symbolSize: chart === "scatter" ? 7 : 4,
                          data: valueX ? result.rows.map((r) => [r[x], r[col]]) : result.rows.map((r) => r[col]),
                          itemStyle: { color: palette[i % palette.length], opacity: chart === "scatter" ? 0.75 : 1, borderRadius: chart === "bar" ? [4, 4, 0, 0] : 0 },
                          lineStyle: { width: 2 },
                        })),
                      };
                    }}
                  />
                ) : chart !== "table" ? <p className="faint">Pick at least one numeric column for y.</p> : null}
              </div>
              <div className="glass card">
                <DataTable columns={columns} rows={result.rows} height={Math.min(420, 40 + result.rows.length * 36)} stickyFirst />
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
