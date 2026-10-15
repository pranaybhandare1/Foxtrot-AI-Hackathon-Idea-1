"""Clean layer: Instinct-era ontology object tables, built from the transformed layer.

Each output table backs one object type in ontology/ontology.yaml (or one of its
datasets), and the ontology step validates keys and links after this runs.
"""

from __future__ import annotations

import json

import polars as pl
from t1d_core.settings import Config

from t1d_pipelines.sources.carelink.clean import alerts, day, devices, glucose, insulin


def build(cfg: Config) -> dict:
    t = cfg.layers.transformed
    a = cfg.analytics
    all_events = pl.read_parquet(t / "carelink_events.parquet")
    era_start = all_events.filter(pl.col("cgm_era") == "instinct")["ts_utc"].min()
    ev = all_events.filter(pl.col("cgm_era") == "instinct")
    minutes = a["glucose_grid_minutes"]

    sensors = devices.cgm_sensors(all_events, era_start)
    sets = devices.infusion_sets(all_events, era_start)
    susp = devices.suspensions(ev)
    clocks = devices.clock_changes(pl.read_parquet(t / "carelink_clock_changes.parquet"), era_start)

    readings = glucose.readings(ev, sensors)
    offsets = ev.select("ts_utc", "utc_offset_min").sort("ts_utc")
    grid = glucose.grid(readings, offsets, sensors, sets, era_start, minutes)
    exc = glucose.excursions(grid, a["thresholds"], minutes, a["excursion_min_minutes"], a["excursion_end_minutes"])
    bgs = glucose.fingersticks(ev, readings, sensors)

    bol, stray_cancels = insulin.boluses(ev)
    wiz = insulin.wizard_calcs(ev, bol)
    meal = insulin.meals(wiz, bol, grid, minutes, a["meal_window_hours"], a["thresholds"])
    exc = _add_insulin_context(exc, bol, meal)

    alert_df = alerts.alerts(ev)
    auto = pl.read_parquet(t / "carelink_daily_auto_insulin.parquet").filter(pl.col("date_device") >= era_start.date())
    days = day.days(grid, bol, meal, exc, alert_df, susp, auto, ev, a["thresholds"], a["valid_day_min_coverage"])

    tables = {
        "glucose_reading": readings,
        "glucose_5min": grid,
        "cgm_sensor": sensors,
        "infusion_set": sets,
        "bolus": bol,
        "bolus_wizard_calc": wiz,
        "meal": meal,
        "glycemic_excursion": exc,
        "pump_alert": alert_df,
        "pump_suspension": susp,
        "fingerstick_bg": bgs,
        "clock_change": clocks,
        "day": days,
    }
    out = cfg.layers.clean
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.write_parquet(out / f"{name}.parquet")
    stats = {
        "era_start_utc": str(era_start),
        "stray_cancel_records": stray_cancels,
        "rows": {k: v.height for k, v in tables.items()},
    }
    (out / "_build_stats.json").write_text(json.dumps(stats, indent=2))
    return stats


def _add_insulin_context(exc: pl.DataFrame, bol: pl.DataFrame, meal: pl.DataFrame) -> pl.DataFrame:
    """For hypo forensics: insulin and carbs in the 4 hours before each excursion started."""
    b = bol.filter(pl.col("units_delivered") > 0).select(pl.col("start_utc").alias("bolus_utc"), "units_delivered")
    m = meal.select(pl.col("ts_utc").alias("meal_utc"), "carbs_g")
    windows = exc.select("excursion_id", "start_utc", (pl.col("start_utc") - pl.duration(hours=4)).alias("window_utc"))
    ctx = (
        windows.join_where(b, pl.col("bolus_utc") <= pl.col("start_utc"), pl.col("bolus_utc") > pl.col("window_utc"))
        .group_by("excursion_id")
        .agg(
            pl.col("units_delivered").sum().round(2).alias("bolus_u_prior_4h"),
            pl.col("bolus_utc").max().alias("_last_bolus"),
        )
    )
    mc = (
        windows.join_where(m, pl.col("meal_utc") <= pl.col("start_utc"), pl.col("meal_utc") > pl.col("window_utc"))
        .group_by("excursion_id")
        .agg(pl.col("carbs_g").sum().alias("carbs_g_prior_4h"))
    )
    return (
        exc.join(ctx, on="excursion_id", how="left")
        .join(mc, on="excursion_id", how="left")
        .with_columns(
            pl.col("bolus_u_prior_4h", "carbs_g_prior_4h").fill_null(0),
            ((pl.col("start_utc") - pl.col("_last_bolus")).dt.total_seconds() / 60)
            .round(1)
            .alias("minutes_since_last_bolus"),
        )
        .drop("_last_bolus")
    )
