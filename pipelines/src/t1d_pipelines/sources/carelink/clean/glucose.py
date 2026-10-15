"""Glucose objects: raw CGM readings, the regular 5-minute grid, excursions, fingerstick BGs."""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

LINEAGE = ["batch_id", "source_file", "source_line"]
SENSOR_MIN, SENSOR_MAX = 40, 400


def _attach_interval(
    df: pl.DataFrame, intervals: pl.DataFrame, id_col: str, start_col: str, ts_col: str = "ts_utc"
) -> pl.DataFrame:
    """As-of join: tag each row with the interval (sensor / infusion set) that started most recently."""
    right = intervals.select(pl.col(id_col), pl.col(start_col).alias("_start")).sort("_start")
    return df.sort(ts_col).join_asof(right, left_on=ts_col, right_on="_start", strategy="backward").drop("_start")


def readings(events: pl.DataFrame, sensors: pl.DataFrame) -> pl.DataFrame:
    """Every distinct Instinct reading as received by the pump.

    The pump sometimes records the same sensor sample twice, 1-3 min apart (late receipt),
    so readings are ~10% denser than one-per-5-min. The grid below collapses them.
    """
    r = (
        events.filter(pl.col("event_type") == "sensor_glucose")
        .select(
            pl.col("event_id").alias("reading_id"),
            "ts_utc",
            "ts_local",
            "date_local",
            "sg_mgdl",
            "utc_offset_min",
            "ts_repaired",
            *LINEAGE,
        )
        .with_columns(
            (pl.col("sg_mgdl") >= SENSOR_MAX).alias("at_upper_limit"),
            (pl.col("sg_mgdl") <= SENSOR_MIN).alias("at_lower_limit"),
        )
    )
    return _attach_interval(r, sensors, "sensor_id", "first_paired_utc")


def grid(
    readings_df: pl.DataFrame,
    offsets: pl.DataFrame,
    sensors: pl.DataFrame,
    sets: pl.DataFrame,
    era_start: datetime,
    minutes: int,
) -> pl.DataFrame:
    """Regular UTC grid over the whole era, gaps included (has_data = false).

    sg_mgdl is the mean of the readings received in the bin. Local time comes from the
    most recent known UTC offset, so the grid stays correct across travel.
    """
    every = f"{minutes}m"
    binned = (
        readings_df.with_columns(pl.col("ts_utc").dt.truncate(every).alias("bin_start_utc"))
        .group_by("bin_start_utc")
        .agg(pl.col("sg_mgdl").mean().round(1).alias("sg_mgdl"), pl.len().alias("n_readings"))
    )
    start = era_start.replace(second=0, microsecond=0) - timedelta(minutes=era_start.minute % minutes)
    end = readings_df["ts_utc"].max()
    g = pl.DataFrame({"bin_start_utc": pl.datetime_range(start, end, every, eager=True)})
    g = (
        g.join(binned, on="bin_start_utc", how="left")
        .with_columns(pl.col("n_readings").fill_null(0), pl.col("sg_mgdl").is_not_null().alias("has_data"))
        .sort("bin_start_utc")
        .join_asof(offsets.sort("ts_utc"), left_on="bin_start_utc", right_on="ts_utc", strategy="backward")
        .with_columns(pl.col("utc_offset_min").fill_null(strategy="backward"))
        .with_columns(
            (pl.col("bin_start_utc") + pl.duration(minutes=pl.col("utc_offset_min"))).alias("bin_start_local")
        )
        .with_columns(pl.col("bin_start_local").dt.date().alias("date_local"))
        .drop("ts_utc")
    )
    g = _attach_interval(g, sensors, "sensor_id", "first_paired_utc", "bin_start_utc")
    g = (
        g.join(sensors.select("sensor_id", "first_reading_utc"), on="sensor_id", how="left")
        .with_columns(
            ((pl.col("bin_start_utc") - pl.col("first_reading_utc")).dt.total_seconds() / 3600)
            .round(2)
            .alias("sensor_age_hours")
        )
        .drop("first_reading_utc")
    )
    g = _attach_interval(g, sets, "set_id", "started_utc", "bin_start_utc")
    g = (
        g.join(sets.select("set_id", pl.col("started_utc").alias("_set_start")), on="set_id", how="left")
        .with_columns(
            ((pl.col("bin_start_utc") - pl.col("_set_start")).dt.total_seconds() / 3600).round(2).alias("set_age_hours")
        )
        .drop("_set_start")
    )
    return g.select(
        "bin_start_utc",
        "bin_start_local",
        "date_local",
        "utc_offset_min",
        "sg_mgdl",
        "n_readings",
        "has_data",
        "sensor_id",
        "sensor_age_hours",
        "set_id",
        "set_age_hours",
    ).sort("bin_start_utc")


def _episodes(
    values: list[float | None], inside, min_bins: int, end_bins: int, max_gap_bins: int
) -> list[tuple[int, int]]:
    """Run-length episode detection on a regular grid.

    Starts after `min_bins` consecutive in-condition bins; ends once `end_bins` consecutive
    bins are out of condition, or the data gap exceeds `max_gap_bins` (end = last inside bin).
    """
    out: list[tuple[int, int]] = []
    run_start = None
    in_episode = False
    ep_start = last_inside = None
    outside_run = gap_run = inside_run = 0
    for i, v in enumerate(values):
        if v is None:
            gap_run += 1
            if gap_run > max_gap_bins:
                if in_episode:
                    out.append((ep_start, last_inside))
                in_episode, inside_run, outside_run = False, 0, 0
            continue
        gap_run = 0
        if inside(v):
            if inside_run == 0:
                run_start = i
            inside_run += 1
            outside_run = 0
            last_inside = i
            if not in_episode and inside_run >= min_bins:
                in_episode, ep_start = True, run_start
        else:
            inside_run = 0
            if in_episode:
                outside_run += 1
                if outside_run >= end_bins:
                    out.append((ep_start, last_inside))
                    in_episode, outside_run = False, 0
    if in_episode:
        out.append((ep_start, last_inside))
    return out


def excursions(g: pl.DataFrame, thresholds: dict, minutes: int, min_minutes: int, end_minutes: int) -> pl.DataFrame:
    """Hypo (<70; level 2 if >=15 min <54) and hyper (>250, i.e. consensus level 2) episodes."""
    min_bins, end_bins = min_minutes // minutes, end_minutes // minutes
    sg = g["sg_mgdl"].to_list()
    rows = []
    specs = [
        ("hypo", lambda v: v < thresholds["low"], min, lambda v: v < thresholds["very_low"]),
        ("hyper", lambda v: v > thresholds["very_high"], max, None),
    ]
    for kind, cond, extreme_fn, level2 in specs:
        for a, b in _episodes(sg, cond, min_bins, end_bins, max_gap_bins=end_bins):
            window = g.slice(a, b - a + 1)
            vals = [v for v in window["sg_mgdl"].to_list() if v is not None]
            level = 2 if kind == "hyper" else 1
            if level2 is not None:
                run = best = 0
                for v in window["sg_mgdl"].to_list():
                    run = run + 1 if (v is not None and level2(v)) else 0
                    best = max(best, run)
                level = 2 if best >= min_bins else 1
            first = window.row(0, named=True)
            last = window.row(-1, named=True)
            rows.append(
                {
                    "excursion_id": f"{kind}_{first['bin_start_utc']:%Y%m%dT%H%M}",
                    "kind": kind,
                    "level": level,
                    "start_utc": first["bin_start_utc"],
                    "end_utc": last["bin_start_utc"] + timedelta(minutes=minutes),
                    "start_local": first["bin_start_local"],
                    "date_local": first["date_local"],
                    "duration_min": (b - a + 1) * minutes,
                    "extreme_sg_mgdl": extreme_fn(vals),
                    "bins_with_data": len(vals),
                    "is_nocturnal": 0 <= first["bin_start_local"].hour < 6,
                    "sensor_id": first["sensor_id"],
                    "sensor_age_hours": first["sensor_age_hours"],
                    "set_id": first["set_id"],
                    "set_age_hours": first["set_age_hours"],
                }
            )
    schema = {
        "excursion_id": pl.Utf8,
        "kind": pl.Utf8,
        "level": pl.Int64,
        "start_utc": pl.Datetime("us"),
        "end_utc": pl.Datetime("us"),
        "start_local": pl.Datetime("us"),
        "date_local": pl.Date,
        "duration_min": pl.Int64,
        "extreme_sg_mgdl": pl.Float64,
        "bins_with_data": pl.Int64,
        "is_nocturnal": pl.Boolean,
        "sensor_id": pl.Utf8,
        "sensor_age_hours": pl.Float64,
        "set_id": pl.Utf8,
        "set_age_hours": pl.Float64,
    }
    return pl.DataFrame(rows, schema=schema).sort("start_utc")


def fingersticks(events: pl.DataFrame, readings_df: pl.DataFrame, sensors: pl.DataFrame) -> pl.DataFrame:
    """Meter BGs. One meter reading produces several pump rows (received / used for check / ...)."""
    bg = (
        events.filter((pl.col("event_type") == "bg_reading") & pl.col("bg_mgdl").is_not_null())
        .sort("ts_utc")
        .with_columns(pl.col("ts_utc").dt.truncate("1m").alias("_minute"))
        .group_by("_minute", "bg_mgdl", maintain_order=True)
        .agg(
            pl.col("event_id").first().alias("bg_id"),
            pl.col("ts_utc").first(),
            pl.col("ts_local").first(),
            pl.col("date_local").first(),
            pl.col("bg_source").unique().sort().str.join("|").alias("bg_sources"),
            *[pl.col(c).first() for c in LINEAGE],
        )
        .drop("_minute")
    )
    near = readings_df.select(
        "ts_utc", pl.col("sg_mgdl").alias("sensor_sg_mgdl"), pl.col("ts_utc").alias("sensor_ts_utc")
    ).sort("ts_utc")
    bg = bg.sort("ts_utc").join_asof(near, on="ts_utc", strategy="nearest", tolerance="5m")
    bg = _attach_interval(bg, sensors, "sensor_id", "first_paired_utc")
    return bg.with_columns(
        (pl.col("sensor_sg_mgdl") - pl.col("bg_mgdl")).alias("sensor_minus_bg_mgdl"),
        ((pl.col("sensor_sg_mgdl") - pl.col("bg_mgdl")).abs() / pl.col("bg_mgdl") * 100)
        .round(2)
        .alias("abs_rel_diff_pct"),
    ).select(
        "bg_id",
        "ts_utc",
        "ts_local",
        "date_local",
        "bg_mgdl",
        "bg_sources",
        "sensor_sg_mgdl",
        "sensor_ts_utc",
        "sensor_minus_bg_mgdl",
        "abs_rel_diff_pct",
        "sensor_id",
        *LINEAGE,
    )
