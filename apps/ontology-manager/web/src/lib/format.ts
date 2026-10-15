/** Number/date formatting used across the app. All dates from the API are local wall-clock strings. */

export const pct = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(digits)}%`;

export const num = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v) ? "–" : v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });

export const signed = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v) ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;

/** Minutes per day spent at a share of the day. */
export const perDay = (share: number | null | undefined) => {
  if (share == null) return "–";
  const minutes = Math.round(share * 1440);
  if (minutes < 60) return `${minutes}m/day`;
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m/day`;
};

/** API datetimes are naive local strings ("2026-08-14T13:05:00"); treat them as UTC for stable math/axes. */
export const ms = (s: string) => Date.parse(s.length === 10 ? `${s}T00:00:00Z` : `${s}Z`);

const two = (n: number) => String(n).padStart(2, "0");

export const hhmm = (s: string | number) => {
  const d = new Date(typeof s === "number" ? s : ms(s));
  return `${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`;
};

export const minuteLabel = (m: number) => `${two(Math.floor(m / 60) % 24)}:${two(m % 60)}`;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export const dateLabel = (s: string, withDow = false) => {
  const d = new Date(ms(s));
  const base = `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
  return withDow ? `${DOW[d.getUTCDay()]}, ${base}` : base;
};

export const dateTimeLabel = (s: string) => `${dateLabel(s, true)} · ${hhmm(s)}`;

export const longDate = (s: string) => {
  const d = new Date(ms(s));
  return `${DOW[d.getUTCDay()]}, ${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
};

/** ISO date arithmetic without timezone surprises. */
export const addDays = (iso: string, days: number) => {
  const d = new Date(ms(iso) + days * 86_400_000);
  return d.toISOString().slice(0, 10);
};

export const daysBetween = (a: string, b: string) => Math.round((ms(b) - ms(a)) / 86_400_000);

export const mondayOf = (iso: string) => {
  const d = new Date(ms(iso));
  const shift = (d.getUTCDay() + 6) % 7;
  return addDays(iso, -shift);
};

export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** Today's local calendar date (+ offset days) as YYYY-MM-DD, for action-form defaults. */
export const localIso = (offsetDays = 0) => {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
