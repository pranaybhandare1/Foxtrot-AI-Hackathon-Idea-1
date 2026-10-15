/** Shared ECharts building blocks that read the live CSS theme, so charts follow light/dark mode. */

import { minuteLabel } from "./format";

export type Palette = {
  text: string;
  muted: string;
  faint: string;
  grid: string;
  glass: string;
  border: string;
  targetBand: string;
  suspend: string;
  insulin: string;
  autoInsulin: string;
  carbs: string;
  accent: string;
};

/** Read theme tokens from `el` (CSS variables inherit, so a white report sheet can override them locally). */
export function readPalette(el: Element = document.documentElement): Palette {
  const css = getComputedStyle(el);
  const v = (name: string) => css.getPropertyValue(name).trim();
  return {
    text: v("--text"),
    muted: v("--text-muted"),
    faint: v("--text-faint"),
    grid: v("--grid-line"),
    glass: v("--glass-strong"),
    border: v("--glass-border"),
    targetBand: v("--target-band"),
    suspend: v("--suspend"),
    insulin: v("--insulin"),
    autoInsulin: v("--auto-insulin"),
    carbs: v("--carbs"),
    accent: v("--accent"),
  };
}

/** Frosted tooltip consistent with the glass surfaces. */
export const tooltip = (p: Palette, extra: Record<string, unknown> = {}) => ({
  backgroundColor: p.glass,
  borderColor: p.border,
  borderWidth: 1,
  padding: [8, 12],
  textStyle: { color: p.text, fontSize: 12 },
  extraCssText: "backdrop-filter: blur(20px) saturate(170%); border-radius: 14px; box-shadow: 0 14px 40px -16px rgba(0,0,0,.6);",
  ...extra,
});

export const axisCommon = (p: Palette) => ({
  axisLine: { lineStyle: { color: p.grid } },
  axisTick: { show: false },
  axisLabel: { color: p.faint, fontSize: 11 },
  splitLine: { lineStyle: { color: p.grid } },
});

/** 00:00 – 24:00 x-axis for time-of-day charts (value = minute of day). */
export const minuteAxis = (p: Palette) => ({
  type: "value" as const,
  min: 0,
  max: 1440,
  interval: 180,
  ...axisCommon(p),
  splitLine: { show: false },
  axisLabel: { color: p.faint, fontSize: 11, formatter: (m: number) => minuteLabel(m) },
});

export const glucoseAxis = (p: Palette, max = 350) => ({
  type: "value" as const,
  min: 40,
  max,
  interval: 50,
  ...axisCommon(p),
  axisLabel: { color: p.faint, fontSize: 11 },
});

/** Shaded 70–180 target band + threshold lines for any glucose series. */
export const targetMarks = (p: Palette) => ({
  markArea: { silent: true, itemStyle: { color: p.targetBand }, data: [[{ yAxis: 70 }, { yAxis: 180 }]] },
  markLine: {
    silent: true,
    symbol: "none",
    label: { show: false },
    lineStyle: { type: "dashed", width: 1 },
    data: [
      { yAxis: 54, lineStyle: { color: "#c2255c", opacity: 0.55 } },
      { yAxis: 70, lineStyle: { color: "#ff5a5f", opacity: 0.55 } },
      { yAxis: 180, lineStyle: { color: "#ffc53d", opacity: 0.55 } },
      { yAxis: 250, lineStyle: { color: "#ff8a3d", opacity: 0.45 } },
    ],
  },
});
