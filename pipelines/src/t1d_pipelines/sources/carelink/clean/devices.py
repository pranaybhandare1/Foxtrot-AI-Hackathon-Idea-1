"""Device-lifecycle objects: CGM sensors, infusion sets, pump suspensions, clock changes."""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

LINEAGE = ["batch_id", "source_file", "source_line"]


def cgm_sensors(events: pl.DataFrame, era_start: datetime) -> pl.DataFrame:
    """One row per Instinct sensor (serial), bounded by pairing events.

    A sensor's window runs from its first 'added' event to the next sensor's first 'added'.
    The pump logs every re-pairing of the same serial, so one sensor can have many adds.
    """
    ble = (
        events.filter((pl.col("event_type") == "ble_device") & (pl.col("ts_utc") >= era_start - timedelta(minutes=5)))
        .with_columns(
            pl.col("ble_device_event").str.extract(r"Unknown device \((\w+)\)").alias("sensor_id"),
            pl.col("ble_device_event").str.extract(r"was (added|removed)").alias("action"),
        )
        .filter(pl.col("sensor_id").is_not_null())
    )
    sessions = (
        ble.group_by("sensor_id")
        .agg(
            pl.col("ts_utc").filter(pl.col("action") == "added").min().alias("first_paired_utc"),
            pl.col("ts_utc").filter(pl.col("action") == "removed").max().alias("removed_utc"),
            (pl.col("action") == "added").sum().alias("n_pairings"),
        )
        .sort("first_paired_utc")
        .with_columns(pl.col("first_paired_utc").shift(-1).alias("window_end_utc"))
    )

    readings = events.filter((pl.col("event_type") == "sensor_glucose") & (pl.col("ts_utc") >= era_start))
    readings = readings.sort("ts_utc").join_asof(
        sessions.select("sensor_id", "first_paired_utc").sort("first_paired_utc"),
        left_on="ts_utc",
        right_on="first_paired_utc",
        strategy="backward",
    )
    stats = readings.group_by("sensor_id").agg(
        pl.col("ts_utc").min().alias("first_reading_utc"),
        pl.col("ts_utc").max().alias("last_reading_utc"),
        pl.len().alias("n_readings"),
        pl.col("ts_utc").dt.truncate("5m").n_unique().alias("bins_with_data"),
    )

    def count_in_window(mask: pl.Expr, name: str) -> pl.DataFrame:
        hits = (
            events.filter(mask & (pl.col("ts_utc") >= era_start))
            .sort("ts_utc")
            .join_asof(
                sessions.select("sensor_id", "first_paired_utc").sort("first_paired_utc"),
                left_on="ts_utc",
                right_on="first_paired_utc",
                strategy="backward",
            )
        )
        return hits.group_by("sensor_id").agg(pl.len().alias(name))

    out = sessions.join(stats, on="sensor_id", how="left")
    for mask, name in [
        (
            (pl.col("event_type") == "sensor_exception") & (pl.col("sensor_exception") == "SENSOR_ERROR"),
            "n_sensor_errors",
        ),
        (
            (pl.col("event_type") == "sensor_exception") & (pl.col("sensor_exception") == "SENSOR_FAILED_BG_CHECK"),
            "n_failed_bg_checks",
        ),
        (
            (pl.col("event_type") == "alert") & pl.col("alert_raw").str.starts_with("LOST SENSOR SIGNAL"),
            "n_signal_loss_alerts",
        ),
    ]:
        out = out.join(count_in_window(mask, name), on="sensor_id", how="left")

    return (
        out.with_columns(
            pl.col("n_sensor_errors", "n_failed_bg_checks", "n_signal_loss_alerts").fill_null(0),
            ((pl.col("first_reading_utc") - pl.col("first_paired_utc")).dt.total_seconds() / 60)
            .round(1)
            .alias("warmup_minutes"),
            ((pl.col("last_reading_utc") - pl.col("first_reading_utc")).dt.total_seconds() / 86400)
            .round(3)
            .alias("wear_days"),
            (((pl.col("last_reading_utc") - pl.col("first_reading_utc")).dt.total_seconds() / 300).floor() + 1)
            .cast(pl.Int64)
            .alias("expected_bins"),
        )
        .with_columns(
            (pl.col("bins_with_data") / pl.col("expected_bins")).round(4).alias("coverage"),
            pl.when(pl.col("window_end_utc").is_null() & pl.col("removed_utc").is_null())
            .then(pl.lit("active_at_export"))
            .when(pl.col("removed_utc").is_not_null())
            .then(pl.lit("removed"))
            .otherwise(pl.lit("replaced"))
            .alias("end_state"),
            (pl.col("wear_days") >= 14).alias("is_full_wear"),
            pl.int_range(1, pl.len() + 1).alias("sensor_number"),
        )
        .select(
            "sensor_id",
            "sensor_number",
            "first_paired_utc",
            "first_reading_utc",
            "last_reading_utc",
            "removed_utc",
            "window_end_utc",
            "end_state",
            "warmup_minutes",
            "wear_days",
            "is_full_wear",
            "n_pairings",
            "n_readings",
            "expected_bins",
            "bins_with_data",
            "coverage",
            "n_sensor_errors",
            "n_failed_bg_checks",
            "n_signal_loss_alerts",
        )
    )


def infusion_sets(events: pl.DataFrame, era_start: datetime) -> pl.DataFrame:
    """Reservoir + infusion-set changes: rewind -> tubing fill -> cannula fill, clustered within 60 min.

    Uses full history so the set already in place when the Instinct era began is included.
    """
    ev = (
        events.filter(pl.col("event_type").is_in(["rewind", "prime"]))
        .sort("ts_utc")
        .with_columns(
            ((pl.col("ts_utc").diff().dt.total_seconds() > 3600) | pl.col("ts_utc").diff().is_null())
            .cum_sum()
            .alias("cluster")
        )
    )
    clusters = (
        ev.group_by("cluster")
        .agg(
            pl.col("ts_utc").min().alias("change_started_utc"),
            pl.col("ts_utc").max().alias("started_utc"),
            pl.col("ts_local").max().alias("started_local"),
            (pl.col("prime_type") == "Tubing Fill").any().alias("has_tubing_fill"),
            pl.col("prime_u").filter(pl.col("prime_type") == "Tubing Fill").sum().alias("tubing_prime_u"),
            pl.col("prime_u").filter(pl.col("prime_type") == "Cannula Fill").sum().alias("cannula_prime_u"),
            pl.col("reservoir_after_fill_u").max().alias("reservoir_fill_u"),
            pl.col("rewind").any().alias("had_rewind"),
            pl.col("batch_id").first(),
            pl.col("source_file").first(),
            pl.col("source_line").first(),
        )
        .filter(pl.col("has_tubing_fill"))
        .sort("started_utc")
        .with_columns(pl.col("started_utc").shift(-1).alias("ended_utc"))
    )
    return (
        clusters.filter(pl.col("ended_utc").is_null() | (pl.col("ended_utc") > era_start))
        .with_columns(
            ("set_" + pl.col("started_local").dt.strftime("%Y%m%dT%H%M")).alias("set_id"),
            ((pl.col("ended_utc") - pl.col("started_utc")).dt.total_seconds() / 3600).round(2).alias("wear_hours"),
            (pl.col("started_utc") < era_start).alias("started_before_era"),
        )
        .select(
            "set_id",
            "change_started_utc",
            "started_utc",
            "started_local",
            "ended_utc",
            "wear_hours",
            "reservoir_fill_u",
            "tubing_prime_u",
            "cannula_prime_u",
            "had_rewind",
            "started_before_era",
            *LINEAGE,
        )
    )


def suspensions(events: pl.DataFrame) -> pl.DataFrame:
    """Periods of no insulin delivery: from a suspend state until the next NORMAL_PUMPING."""
    rows = events.filter(pl.col("event_type") == "suspend_state").sort("ts_utc")
    out, current = [], None
    for r in rows.iter_rows(named=True):
        if r["suspend_state"] != "NORMAL_PUMPING":
            if current is None:
                current = {
                    "suspension_id": "susp_" + r["event_id"],
                    "start_utc": r["ts_utc"],
                    "start_local": r["ts_local"],
                    "date_local": r["date_local"],
                    "reason": r["suspend_state"],
                    "reasons": [r["suspend_state"]],
                    "batch_id": r["batch_id"],
                    "source_file": r["source_file"],
                    "source_line": r["source_line"],
                }
            elif r["suspend_state"] not in current["reasons"]:
                current["reasons"].append(r["suspend_state"])
        elif current is not None:
            current["end_utc"] = r["ts_utc"]
            out.append(current)
            current = None
    if current is not None:
        current["end_utc"] = None
        out.append(current)
    schema = {
        "suspension_id": pl.Utf8,
        "start_utc": pl.Datetime("us"),
        "start_local": pl.Datetime("us"),
        "date_local": pl.Date,
        "reason": pl.Utf8,
        "reasons": pl.List(pl.Utf8),
        "batch_id": pl.Utf8,
        "source_file": pl.Utf8,
        "source_line": pl.Int64,
        "end_utc": pl.Datetime("us"),
    }
    df = pl.DataFrame(out, schema=schema)
    return df.with_columns(
        ((pl.col("end_utc") - pl.col("start_utc")).dt.total_seconds() / 60).round(2).alias("duration_min"),
        pl.col("reasons").list.join("|"),
    ).select(
        "suspension_id",
        "start_utc",
        "start_local",
        "end_utc",
        "duration_min",
        "date_local",
        "reason",
        "reasons",
        "batch_id",
        "source_file",
        "source_line",
    )


def clock_changes(transformed_clock: pl.DataFrame, era_start: datetime) -> pl.DataFrame:
    return (
        transformed_clock.filter(pl.col("ts_utc") >= era_start)
        .with_columns(
            ("clk_" + pl.col("ts_utc").dt.strftime("%Y%m%dT%H%M%S")).alias("clock_change_id"),
            (pl.col("delta_min").abs() >= 30).alias("is_timezone_change"),
        )
        .select(
            "clock_change_id",
            "ts_utc",
            "ts_device_old",
            "ts_device_new",
            "delta_min",
            "device_offset_min_before",
            "device_offset_min_after",
            "is_timezone_change",
            "batch_id",
        )
    )
