"""Pump alerts, normalized and matched to the user's clear action."""

from __future__ import annotations

import polars as pl

LINEAGE = ["batch_id", "source_file", "source_line"]

# first matching keyword wins
CATEGORIES = [
    ("glucose_low", ["ON LOW", "URGENT LOW", "BEFORE LOW", "SUSPEND ON LOW", "LOW SG"]),
    ("glucose_high", ["ON HIGH", "PROLONGED HIGH"]),
    ("smartguard", ["SMARTGUARD"]),
    ("sensor", ["SENSOR", "CALIBRATION"]),
    (
        "insulin_delivery",
        ["RESERVOIR", "INSULIN FLOW", "BOLUS NOT DELIVERED", "CANNULA", "REWIND", "BASAL DELIVERY", "LOADING"],
    ),
    ("power", ["BATTERY", "POWER"]),
    ("pump_device", ["PUMP", "BUTTON", "PAIRING"]),
]


def _category() -> pl.Expr:
    expr = pl.lit("other")
    for name, words in reversed(CATEGORIES):
        expr = pl.when(pl.col("alert_type").str.contains("|".join(words))).then(pl.lit(name)).otherwise(expr)
    return expr.alias("category")


def alerts(events: pl.DataFrame, clear_window_hours: int = 3) -> pl.DataFrame:
    """'ALERT ON LOW: siren (62)' -> type ALERT ON LOW, channel siren, value 62.

    cleared_utc = first 'User Cleared Alerts' of the same type after the alert (within 3 h),
    so response_minutes measures how long an alert went unanswered.
    """
    a = (
        events.filter(pl.col("event_type") == "alert")
        .with_columns(
            pl.col("alert_raw")
            .str.extract(r"^(.*?):")
            .str.replace(r", QUIET$", "")
            .str.strip_chars()
            .alias("alert_type"),
            pl.col("alert_raw").str.extract(r":\s*(\w+)").alias("channel"),
            pl.col("alert_raw").str.extract(r"\((\d+)\)").cast(pl.Float64).alias("value_mgdl"),
            pl.col("alert_raw").str.contains("QUIET").alias("is_quiet"),
        )
        .with_columns(_category())
        .select(
            pl.col("event_id").alias("alert_id"),
            "ts_utc",
            "ts_local",
            "date_local",
            "alert_type",
            "category",
            "channel",
            "value_mgdl",
            "is_quiet",
            "alert_raw",
            *LINEAGE,
        )
        .sort("ts_utc")
    )
    clears = (
        events.filter(pl.col("event_type") == "alert_cleared")
        .select(pl.col("alert_cleared").str.strip_chars().alias("alert_type"), pl.col("ts_utc").alias("cleared_utc"))
        .sort("cleared_utc")
    )
    a = a.join_asof(
        clears,
        left_on="ts_utc",
        right_on="cleared_utc",
        by="alert_type",
        strategy="forward",
        check_sortedness=False,
        tolerance=f"{clear_window_hours}h",
    )
    return a.with_columns(
        ((pl.col("cleared_utc") - pl.col("ts_utc")).dt.total_seconds() / 60).round(2).alias("response_minutes")
    )
