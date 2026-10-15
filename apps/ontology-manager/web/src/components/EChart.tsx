/**
 * Thin ECharts wrapper: owns the instance, resizes with its container, re-themes on light/dark
 * switch, and forwards events. Options are rebuilt by callers via `build(palette)`.
 * Interactive views (e.g. the glucose explorer) can take the instance via `onInit` to drive zoom
 * directly without rebuilding the option.
 */

import * as echarts from "echarts";
import { useEffect, useRef } from "react";
import { readPalette, type Palette } from "../lib/chartTheme";
import { useTheme } from "../state/theme";

/** ECharts options are deeply dynamic; builders return plain objects, validated by ECharts at runtime. */
export type ChartOption = Record<string, any>;

type Props = {
  build: (p: Palette) => ChartOption;
  height?: number | string;
  onClick?: (params: any) => void;
  /** Extra ECharts events, e.g. { datazoom: (e, chart) => … }. */
  events?: Record<string, (params: any, chart: echarts.ECharts) => void>;
  onInit?: (chart: echarts.ECharts) => void;
  /** Disable the entry animation (large or frequently rebuilt charts). */
  animate?: boolean;
  deps: unknown[];
};

export function EChart({ build, height = 300, onClick, events, onInit, animate = true, deps }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const { resolved } = useTheme();
  const handlers = useRef({ onClick, events, onInit });

  useEffect(() => {
    handlers.current = { onClick, events, onInit };
  }, [onClick, events, onInit]);

  useEffect(() => {
    if (!el.current) return;
    const instance = echarts.init(el.current, undefined, { renderer: "canvas" });
    chart.current = instance;
    instance.on("click", (p) => handlers.current.onClick?.(p));
    for (const name of Object.keys(handlers.current.events ?? {})) {
      instance.on(name, (p) => handlers.current.events?.[name]?.(p, instance));
    }
    handlers.current.onInit?.(instance);
    const ro = new ResizeObserver(() => instance.resize({ animation: { duration: 200 } }));
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  // Rebuild the option only when a declared dependency (or the theme) changes identity.
  const previous = useRef<unknown[] | null>(null);
  useEffect(() => {
    const next = [...deps, resolved];
    const same = previous.current?.length === next.length && next.every((d, i) => Object.is(d, previous.current![i]));
    if (same || !chart.current) return;
    previous.current = next;
    chart.current.setOption(
      {
        backgroundColor: "transparent",
        animation: animate,
        animationDuration: 500,
        animationEasing: "cubicOut",
        useUTC: true,
        ...build(readPalette(el.current ?? undefined)),
      } as echarts.EChartsOption,
      { notMerge: true },
    );
  });

  return <div ref={el} style={{ width: "100%", height }} />;
}
