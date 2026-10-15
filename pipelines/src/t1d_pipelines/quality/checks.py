"""Data-quality checks across every layer. Writes reports/data_quality.md (+ .json).

Severity: error = the build fails; warn = look at it; info = context you should know.
Each check returns (passed, detail). Checks encode what we learned profiling this source,
so a future export that breaks an assumption fails loudly instead of silently skewing insights.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, timedelta

import polars as pl
from t1d_core.settings import Config


@dataclass
class CheckResult:
    check_id: str
    layer: str
    severity: str
    title: str
    passed: bool
    detail: str

    @property
    def status(self) -> str:
        if self.passed:
            return "PASS"
        return {"error": "FAIL", "warn": "WARN", "info": "NOTE"}[self.severity]


class Ctx:
    """Lazy loader for layer tables."""

    def __init__(self, cfg: Config):
        self.cfg, self._cache = cfg, {}

    def __call__(self, layer: str, name: str) -> pl.DataFrame:
        key = (layer, name)
        if key not in self._cache:
            self._cache[key] = pl.read_parquet(getattr(self.cfg.layers, layer) / f"{name}.parquet")
        return self._cache[key]


CHECKS: list[tuple[str, str, str, str, Callable[[Ctx], tuple[bool, str]]]] = []


def check(check_id: str, layer: str, severity: str, title: str):
    def register(fn):
        CHECKS.append((check_id, layer, severity, title, fn))
        return fn

    return register


# ---------------------------------------------------------------- landing / raw
@check("L1", "landing", "error", "Landed files are byte-identical to what was recorded at landing")
def _(c: Ctx):
    batches = sorted((c.cfg.layers.landing / "carelink").glob("export_*/_manifest.json"))
    files, changed = 0, []
    for b in batches:
        for f in json.loads(b.read_text())["files"]:
            files += 1
            if hashlib.sha256((b.parent / f["file"]).read_bytes()).hexdigest() != f["sha256"]:
                changed.append(f"{b.parent.name}/{f['file']}")
    return not changed, f"{files} files in {len(batches)} batch(es); changed since landing: {changed or 'none'}"


@check("L3", "landing", "warn", "Every landed file is listed in the export's checksums.sha256")
def _(c: Ctx):
    batches = sorted((c.cfg.layers.landing / "carelink").glob("export_*/_manifest.json"))
    files = [f for b in batches for f in json.loads(b.read_text())["files"]]
    bad = sorted({f["file"] for f in files if not f["checksum_verified"]})
    detail = (
        "all listed and verified"
        if not bad
        else (
            f"not in checksums.sha256 (hash recorded at landing instead): {bad}. "
            "Add them to ~/CareLink-raw/checksums.sha256 to verify against the source."
        )
    )
    return not bad, detail


@check("L2", "landing", "error", "Export windows are contiguous (no gaps, no overlaps)")
def _(c: Ctx):
    meta = c("raw", "carelink_file_metadata").with_columns(
        pl.col("source_file").str.extract(r"_(\d{4}-\d{2}-\d{2})_to_").str.to_date().alias("start"),
        pl.col("source_file").str.extract(r"_to_(\d{4}-\d{2}-\d{2})").str.to_date().alias("end"),
    )
    problems = []
    for batch in meta["batch_id"].unique():
        m = meta.filter(pl.col("batch_id") == batch).sort("start")
        for prev_end, start in zip(m["end"][:-1], m["start"][1:], strict=True):
            if start != prev_end + timedelta(days=1):
                problems.append(f"{prev_end} -> {start}")
    return not problems, "windows chain day-to-day" if not problems else f"breaks: {problems}"


@check("R1", "raw", "error", "Every file has the pump, aggregated-insulin and sensor sections")
def _(c: Ctx):
    m = c("raw", "carelink_file_metadata")
    bad = m.filter(
        (pl.col("rows_pump") == 0) | (pl.col("rows_pump_aggregated_auto_insulin") == 0) | (pl.col("rows_sensor") == 0)
    )["source_file"].to_list()
    return (
        not bad,
        f"{m.height} files, {m['rows_pump'].sum() + m['rows_sensor'].sum() + m['rows_pump_aggregated_auto_insulin'].sum():,} rows; missing sections in: {bad or 'none'}",
    )


@check("R2", "raw", "warn", "All files come from the same pump serial")
def _(c: Ctx):
    serials = sorted({s for v in c("raw", "carelink_file_metadata")["serial_number"] for s in v.split("|")})
    return len(serials) == 1, f"serials: {serials}"


# ---------------------------------------------------------------- transformed
@check("T1", "transformed", "info", "Rows that carry no payload (dropped from clean)")
def _(c: Ctx):
    ev = c("transformed", "carelink_events")
    n = ev.filter(pl.col("event_type").is_in(["empty", "sensor_day_marker"])).height
    return n == 0, f"{n:,} payload-less rows (pump rows with only a timestamp, sensor start/end-of-day markers)"


@check("T2", "transformed", "error", "Pump events: reconstructed UTC is monotonic in pump sequence")
def _(c: Ctx):
    p = (
        c("transformed", "carelink_events")
        .filter(pl.col("section") == "pump")
        .sort(["batch_id", "seq"])
        .with_columns(pl.col("ts_utc").diff().over("batch_id").dt.total_seconds().alias("d"))
    )
    n = p.filter(pl.col("d") < -60).height
    return n == 0, f"{n} backward steps > 60 s across {p.height:,} pump events"


@check("T3", "transformed", "error", "Sensor rows: reconstructed UTC is monotonic in receipt sequence")
def _(c: Ctx):
    s = (
        c("transformed", "carelink_events")
        .filter((pl.col("section") == "sensor") & (pl.col("event_type") != "sensor_day_marker"))
        .sort(["batch_id", "seq"])
        .with_columns(pl.col("ts_utc").diff().over("batch_id").dt.total_seconds().alias("d"))
    )
    n = s.filter(pl.col("d") < -120).height
    return n == 0, f"{n} backward steps > 2 min across {s.height:,} sensor rows"


@check("T4", "transformed", "info", "Timestamps repaired (whole-day sensor clock errors)")
def _(c: Ctx):
    ev = c("transformed", "carelink_events")
    r = ev.filter(pl.col("ts_repaired"))
    return r.is_empty(), f"{r.height} rows repaired: {r.group_by('event_type').len().rows()}"


@check("T5", "transformed", "error", "Pump and sensor clocks agree in every clock segment (alert values vs CGM)")
def _(c: Ctx):
    ev = c("transformed", "carelink_events").filter(pl.col("cgm_era") == "instinct")
    sg = ev.filter(pl.col("event_type") == "sensor_glucose").select("ts_utc", "sg_mgdl").sort("ts_utc")
    al = (
        ev.filter(pl.col("event_type") == "alert")
        .with_columns(pl.col("alert_raw").str.extract(r"\((\d+)\)").cast(pl.Float64).alias("v"))
        .filter(pl.col("v").is_not_null())
        .select("ts_utc", "v", "utc_offset_min")
        .sort("ts_utc")
    )
    bad, notes = [], []
    for offset in al["utc_offset_min"].unique().sort():
        a = al.filter(pl.col("utc_offset_min") == offset)
        err = {}
        for shift in (-60, -10, -5, 0, 5, 10, 60):
            j = a.with_columns((pl.col("ts_utc") + pl.duration(minutes=shift)).alias("ts_utc")).join_asof(
                sg, on="ts_utc", strategy="nearest", tolerance="3m"
            )
            err[shift] = float((j["sg_mgdl"] - j["v"]).abs().median() or 999)
        best = min(err, key=err.get)
        notes.append(
            f"UTC{offset / 60:+.0f}h n={a.height} best shift {best:+d} min (err {err[best]:.0f} vs ±60 min {min(err[-60], err[60]):.0f})"
        )
        if abs(best) > 10 or min(err[-60], err[60]) <= err[best]:
            bad.append(offset)
    return not bad, "; ".join(notes)


@check("T6", "transformed", "error", "Instinct era has no ISIG values (Abbott sensors don't report ISIG)")
def _(c: Ctx):
    ev = c("transformed", "carelink_events")
    n = ev.filter((pl.col("cgm_era") == "instinct") & pl.col("isig").is_not_null()).height
    first = ev.filter((pl.col("cgm_era") == "instinct") & (pl.col("event_type") == "sensor_glucose"))["ts_utc"].min()
    return n == 0, f"{n} ISIG values after era start; first Instinct reading {first} UTC"


@check("T7", "transformed", "info", "Cross-row duplicates removed")
def _(c: Ctx):
    raw_n = c("raw", "carelink_events").height
    ev_n = c("transformed", "carelink_events").height + c("transformed", "carelink_daily_auto_insulin").height
    return raw_n == ev_n, f"raw {raw_n:,} rows -> transformed {ev_n:,} ({raw_n - ev_n:,} exact duplicates collapsed)"


# ---------------------------------------------------------------- clean
@check("C1", "clean", "error", "CGM values are within the sensor's reportable range (40-400)")
def _(c: Ctx):
    r = c("clean", "glucose_reading")
    n = r.filter((pl.col("sg_mgdl") < 40) | (pl.col("sg_mgdl") > 400)).height
    return n == 0, f"{n} out-of-range of {r.height:,}; {r['at_upper_limit'].sum()} at 400 (= '>=400')"


@check("C2", "clean", "error", "5-min grid: at most 3 readings per bin, every bin has a UTC offset")
def _(c: Ctx):
    g = c("clean", "glucose_5min")
    ok = g["n_readings"].max() <= 3 and g["utc_offset_min"].null_count() == 0
    return ok, (f"{g.height:,} bins, {g['has_data'].mean():.1%} with data, max {g['n_readings'].max()} readings/bin")


@check("C3", "clean", "warn", "Sensors: wear <= 15.5 days and coverage >= 90%")
def _(c: Ctx):
    s = c("clean", "cgm_sensor")
    bad = s.filter((pl.col("wear_days") > 15.5) | (pl.col("coverage") < 0.9))["sensor_id"].to_list()
    short = s.filter(~pl.col("is_full_wear") & (pl.col("end_state") != "active_at_export"))
    return not bad, (
        f"{s.height} sensors, median wear {s['wear_days'].median():.1f} d, median coverage "
        f"{s['coverage'].median():.1%}; ended early (<14 d): "
        f"{short.select('sensor_id', 'wear_days').rows() or 'none'}; flagged: {bad or 'none'}"
    )


@check("C4", "clean", "error", "Boluses: delivered <= programmed, non-negative delivery time")
def _(c: Ctx):
    b = c("clean", "bolus")
    over = b.filter(pl.col("units_delivered") > pl.col("units_programmed") + 1e-6).height
    neg = b.filter(pl.col("delivery_minutes") < 0).height
    return (
        over == 0 and neg == 0,
        f"{b.height} boluses; over-delivered {over}; negative duration {neg}; partial {b['is_partial'].sum()}",
    )


@check("C5", "clean", "error", "Every delivered wizard calculation links to a bolus")
def _(c: Ctx):
    w = c("clean", "bolus_wizard_calc").filter(pl.col("status") == "Delivered")
    linked = w["bolus_id"].is_not_null().mean()
    return linked >= 0.99, f"{linked:.1%} of {w.height} delivered wizard calcs linked"


@check("C6", "clean", "error", "Day totals reconcile with their objects (insulin, carbs, hypos)")
def _(c: Ctx):
    d, b, m, e = c("clean", "day"), c("clean", "bolus"), c("clean", "meal"), c("clean", "glycemic_excursion")
    diffs = {
        "bolus_u": d["bolus_u"].sum() - (b["units_delivered"].sum() or 0),
        "carbs_g": d["carbs_g"].sum() - m["carbs_g"].sum(),
        "n_hypo": d["n_hypo"].sum() - e.filter(pl.col("kind") == "hypo").height,
    }
    return all(abs(v) < 1e-6 for v in diffs.values()), f"differences: {diffs}"


@check("C7", "clean", "error", "Excursions of the same kind never overlap")
def _(c: Ctx):
    e = c("clean", "glycemic_excursion").sort("start_utc")
    n = (
        e.with_columns(pl.col("end_utc").shift(1).over("kind").alias("prev_end"))
        .filter(pl.col("start_utc") < pl.col("prev_end"))
        .height
    )
    return n == 0, f"{n} overlaps among {e.height} excursions"


@check("C8", "clean", "warn", "Days with CGM coverage below 70%")
def _(c: Ctx):
    d = c("clean", "day")
    low = d.filter(pl.col("cgm_coverage") < 0.7)
    return (
        low.is_empty(),
        f"{low.height} of {d.height} days: {[(str(day_), cov) for day_, cov in low.select('date_local', 'cgm_coverage').rows()]}",
    )


@check("C9", "clean", "warn", "Total daily dose within a plausible band (10-150 U) on full days")
def _(c: Ctx):
    d = c("clean", "day").filter(~pl.col("is_partial_day"))
    odd = d.filter(~pl.col("tdd_u").is_between(10, 150) | pl.col("tdd_u").is_null())
    return (
        odd.is_empty(),
        f"median TDD {d['tdd_u'].median():.1f} U; outside band: {[(str(day_), tdd) for day_, tdd in odd.select('date_local', 'tdd_u').rows()]}",
    )


@check("C10", "clean", "info", "Infusion sets replaced within 12 h (possible site failures)")
def _(c: Ctx):
    s = c("clean", "infusion_set")
    short = s.filter(pl.col("wear_hours") < 12)
    return (
        short.is_empty(),
        f"{s.height} sets, median wear {s['wear_hours'].median():.0f} h; <12 h: {short.select('set_id', 'wear_hours').rows()}",
    )


@check("C11", "clean", "info", "Sensor vs fingerstick agreement (MARD)")
def _(c: Ctx):
    f = c("clean", "fingerstick_bg").filter(pl.col("sensor_sg_mgdl").is_not_null())
    return True, (
        f"{f.height} paired fingersticks: MARD {f['abs_rel_diff_pct'].mean():.1f}%, median bias "
        f"{f['sensor_minus_bg_mgdl'].median():+.0f} mg/dL (sensor minus meter)"
    )


# ---------------------------------------------------------------- oura
@check("O1", "clean", "warn", "Oura covers most CGM days (readiness present)")
def _(c: Ctx):
    d, o = c("clean", "day"), c("clean", "oura_day")
    if "readiness_score" not in o.columns:
        return False, "no Oura data (run make oura-pull)"
    share = o.filter(pl.col("readiness_score").is_not_null()).height / max(d.height, 1)
    return share >= 0.8, f"{share:.0%} of {d.height} CGM days have an Oura readiness score"


@check("O2", "transformed", "warn", "Local time agrees with Oura's observed time zone on every night")
def _(c: Ctx):
    sleep = c("transformed", "oura_sleep").filter(pl.col("sleep_type") == "long_sleep")
    nights = sleep.select("date_local", pl.col("utc_offset_min").alias("oura")).unique("date_local", keep="last")
    j = c("clean", "day").select("date_local", "utc_offset_min").join(nights, on="date_local")
    bad = j.filter(pl.col("utc_offset_min") != pl.col("oura"))
    return (
        bad.is_empty(),
        f"{j.height - bad.height}/{j.height} nights agree; disagreeing: {[str(x) for x in bad['date_local'].to_list()]}",
    )


@check("O3", "transformed", "info", "Pump-clock local times corrected using Oura")
def _(c: Ctx):
    ev = c("transformed", "carelink_events").filter(pl.col("cgm_era") == "instinct")
    n = ev.filter(pl.col("tz_basis").str.starts_with("oura")).height
    days = ev.filter(pl.col("tz_basis").str.starts_with("oura"))["date_local"].unique().len()
    return (
        n == 0,
        f"{n:,} events on {days} days re-timed to Oura's observed time zone (wrong pump clock or trips without a pump clock change)",
    )


@check("O4", "clean", "error", "Sleep sessions are well-formed (end after start, sleep <= time in bed)")
def _(c: Ctx):
    s = c("clean", "sleep_session")
    bad = s.filter(
        (pl.col("bedtime_end_utc") <= pl.col("bedtime_start_utc"))
        | (pl.col("total_sleep_min") > pl.col("time_in_bed_min") + 1)
    )
    return bad.is_empty(), f"{bad.height} malformed of {s.height} sessions"


@check("O5", "clean", "error", "Heart rate is physiological (25-230 bpm)")
def _(c: Ctx):
    h = c("clean", "heart_rate_5min")
    bad = h.filter((pl.col("mean_bpm") < 25) | (pl.col("max_bpm") > 230))
    return bad.is_empty(), f"{bad.height} out-of-range of {h.height:,} 5-min bins"


# ---------------------------------------------------------------- runner
KNOWN_LIMITATIONS = [
    "SmartGuard auto basal and auto-correction boluses exist only as a **daily total** "
    '(`Day.auto_insulin_u`). Per-meal questions like "how much did the loop add after dinner" can\'t be '
    "answered from this export. User boluses are exact.",
    "The CSV's daily auto-insulin total under-counts auto-corrections vs. CareLink's PDF (~5-7 U/day, ~9% of TDD on "
    "recent days); see docs/data-sources/carelink.md.",
    "`InfusionSet` marks reservoir/tubing fills; true infusion-set changes (~every 3.3 days) are not yet distinguished.",
    "Meals are wizard carb entries. Food eaten without a wizard entry (e.g. treating a low) is invisible.",
    "Local time assumes the final pump clock was UTC-4 (EDT) at export and home = America/New_York (New Jersey) "
    "(config). Every earlier clock segment is derived from the logged clock changes, and T5 validates it independently.",
    "Local time follows the pump clock, corrected by Oura's observed phone time zone where they disagree (O2/O3); "
    "days without Oura data rely on the pump clock alone.",
    "The manual basal schedule (1.3 / 1.35 U/h) is kept in transformed but is not delivered while SmartGuard is active.",
    "Backward clock changes smaller than the CGM receipt interval can mis-time a few readings by at most |change| "
    "(<= 1 min in this data).",
]


def run(cfg: Config) -> dict:
    ctx = Ctx(cfg)
    results = []
    for check_id, layer, severity, title, fn in CHECKS:
        try:
            passed, detail = fn(ctx)
        except Exception as exc:  # a crashing check is a failing check
            passed, detail = False, f"check raised {type(exc).__name__}: {exc}"
        results.append(CheckResult(check_id, layer, severity, title, bool(passed), detail))

    failed = [r for r in results if r.status == "FAIL"]
    stats = json.loads((cfg.layers.clean / "_build_stats.json").read_text())
    days = ctx("clean", "day")
    lines = [
        "# Data quality report: CareLink (Instinct era)",
        "",
        f"_Generated {date.today()} by `t1d run`._",
        "",
        f"- Instinct era: **{days['date_local'].min()} → {days['date_local'].max()}** "
        f"({days.height} days, {days['is_valid_cgm_day'].sum()} valid CGM days)",
        f"- Result: **{sum(r.passed for r in results)}/{len(results)} checks passed**, "
        f"{len(failed)} failing errors, {sum(r.status == 'WARN' for r in results)} warnings",
        "",
        "| ID | Layer | Severity | Status | Check | Detail |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.check_id} | {r.layer} | {r.severity} | **{r.status}** | {r.title} | {r.detail} |")
    lines += ["", "## Clean-layer row counts", "", "| Table | Rows |", "|---|---|"]
    lines += [f"| {k} | {v:,} |" for k, v in stats["rows"].items()]
    lines += ["", "## Known limitations of this source", ""] + [f"- {x}" for x in KNOWN_LIMITATIONS]

    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    (cfg.reports_dir / "data_quality.md").write_text("\n".join(lines) + "\n")
    (cfg.reports_dir / "data_quality.json").write_text(
        json.dumps([asdict(r) | {"status": r.status} for r in results], indent=2)
    )
    return {
        "checks": len(results),
        "passed": sum(r.passed for r in results),
        "failed": [r.check_id for r in failed],
        "warnings": [r.check_id for r in results if r.status == "WARN"],
    }
