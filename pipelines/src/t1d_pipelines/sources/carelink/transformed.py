"""Transformed layer: typed, classified, time-corrected, deduplicated CareLink events.

Input : raw/carelink_events.parquet (strings, one row per source row, all batches)
Output: transformed/
  carelink_events.parquet             one row per distinct pump/sensor event, typed + UTC
  carelink_daily_auto_insulin.parquet one row per device-date of SmartGuard auto insulin
  carelink_clock_changes.parquet      every pump clock change with its inferred offsets

Nothing is scoped out here: pre-Instinct history is kept and tagged with cgm_era.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import polars as pl
from t1d_core.settings import Config, parse_utc_offset

from t1d_pipelines.sources.carelink.clock import (
    ClockChange,
    LocalTimeResolver,
    ObservedTimeZones,
    pump_segments,
    receipt_segments,
    repair_day_spikes,
    segment_corrections,
    zone_change_times,
)

DT_FMT = "%Y/%m/%d %H:%M:%S"
LINEAGE = ["_batch_id", "_source_file", "_source_line", "_file_sha256", "_section"]
NON_PAYLOAD = {"Index", "Date", "Time", *LINEAGE}

# raw column -> (clean name, dtype)
TYPED_COLUMNS: dict[str, tuple[str, type[pl.DataType] | pl.DataType]] = {
    "Sensor Glucose (mg/dL)": ("sg_mgdl", pl.Float64),
    "ISIG Value": ("isig", pl.Float64),
    "Sensor Exception": ("sensor_exception", pl.Utf8),
    "BG Reading (mg/dL)": ("bg_mgdl", pl.Float64),
    "BG Source": ("bg_source", pl.Utf8),
    "Linked BG Meter ID": ("bg_meter_id", pl.Utf8),
    "System BG Check (mg/dL)": ("system_bg_check_mgdl", pl.Float64),
    "Sensor System BG Check Rejected Reason": ("bg_check_rejected_reason", pl.Utf8),
    "Basal Rate (U/h)": ("basal_rate_u_per_h", pl.Float64),
    "Temp Basal Amount": ("temp_basal_amount", pl.Float64),
    "Temp Basal Type": ("temp_basal_type", pl.Utf8),
    "Temp Basal Duration (h:mm:ss)": ("temp_basal_duration", pl.Utf8),
    "Preset Temp Basal Name": ("temp_basal_preset", pl.Utf8),
    "Bolus Type": ("bolus_type", pl.Utf8),
    "Bolus Volume Selected (U)": ("bolus_selected_u", pl.Float64),
    "Bolus Volume Delivered (U)": ("bolus_delivered_u", pl.Float64),
    "Bolus Duration (h:mm:ss)": ("bolus_duration", pl.Utf8),
    "Bolus Number": ("bolus_number", pl.Int64),
    "Bolus Cancellation Reason": ("bolus_cancel_reason", pl.Utf8),
    "Bolus Source": ("bolus_source", pl.Utf8),
    "Preset Bolus": ("bolus_preset", pl.Utf8),
    "Prime Type": ("prime_type", pl.Utf8),
    "Prime Volume Delivered (U)": ("prime_u", pl.Float64),
    "Estimated Reservoir Volume after Fill (U)": ("reservoir_after_fill_u", pl.Float64),
    "Alert": ("alert_raw", pl.Utf8),
    "User Cleared Alerts": ("alert_cleared", pl.Utf8),
    "Suspend": ("suspend_state", pl.Utf8),
    "Rewind": ("rewind", pl.Utf8),
    "BWZ Estimate (U)": ("bwz_estimate_u", pl.Float64),
    "BWZ Target High BG (mg/dL)": ("bwz_target_high_mgdl", pl.Float64),
    "BWZ Target Low BG (mg/dL)": ("bwz_target_low_mgdl", pl.Float64),
    "BWZ Carb Ratio (g/U)": ("bwz_carb_ratio_g_per_u", pl.Float64),
    "BWZ Insulin Sensitivity (mg/dL/U)": ("bwz_isf_mgdl_per_u", pl.Float64),
    "BWZ Carb Input (grams)": ("bwz_carbs_g", pl.Float64),
    "BWZ BG/SG Input (mg/dL)": ("bwz_bg_input_mgdl", pl.Float64),
    "BWZ Correction Estimate (U)": ("bwz_correction_estimate_u", pl.Float64),
    "BWZ Food Estimate (U)": ("bwz_food_estimate_u", pl.Float64),
    "BWZ Active Insulin (U)": ("bwz_active_insulin_u", pl.Float64),
    "BWZ Status": ("bwz_status", pl.Utf8),
    "BWZ Unabsorbed Insulin Total (U)": ("bwz_unabsorbed_insulin_u", pl.Float64),
    "Final Bolus Estimate": ("bwz_final_estimate_u", pl.Float64),
    "Scroll Step Size": ("scroll_step_size", pl.Utf8),
    "Insulin Action Curve Time": ("insulin_action_curve_min", pl.Float64),
    "Event Marker": ("event_marker", pl.Utf8),
    "BLE Network Device": ("ble_device_event", pl.Utf8),
    "Device Update Event": ("device_update_event", pl.Utf8),
    "Network Device Associated Reason": ("network_associated_reason", pl.Utf8),
    "Network Device Disassociated Reason": ("network_disassociated_reason", pl.Utf8),
    "Network Device Disconnected Reason": ("network_disconnected_reason", pl.Utf8),
    "Sensor State": ("sensor_state", pl.Utf8),
    "New Device Time": ("new_device_time", pl.Utf8),
}

# First matching rule wins. Order matters: e.g. a 'Basal Rate + Suspend' row is a suspend.
PUMP_RULES: list[tuple[str, pl.Expr]] = [
    ("clock_change", pl.col("New Device Time").is_not_null()),
    ("bolus_canceled", pl.col("Bolus Type").is_not_null() & pl.col("Bolus Cancellation Reason").is_not_null()),
    ("bolus_delivered", pl.col("Bolus Type").is_not_null() & pl.col("Bolus Volume Delivered (U)").is_not_null()),
    ("bolus_programmed", pl.col("Bolus Type").is_not_null()),
    ("bolus_wizard", pl.col("BWZ Status").is_not_null()),
    (
        "bolus_wizard_detail",
        pl.col("Final Bolus Estimate").is_not_null() | pl.col("BWZ Unabsorbed Insulin Total (U)").is_not_null(),
    ),
    ("temp_basal", pl.col("Temp Basal Amount").is_not_null() | pl.col("Temp Basal Type").is_not_null()),
    ("prime", pl.col("Prime Type").is_not_null()),
    ("rewind", pl.col("Rewind").is_not_null()),
    ("suspend_state", pl.col("Suspend").is_not_null()),
    ("basal_rate_change", pl.col("Basal Rate (U/h)").is_not_null()),
    ("alert", pl.col("Alert").is_not_null()),
    ("alert_cleared", pl.col("User Cleared Alerts").is_not_null()),
    ("system_bg_check", pl.col("System BG Check (mg/dL)").is_not_null()),
    ("bg_reading", pl.col("BG Reading (mg/dL)").is_not_null() | pl.col("BG Source").is_not_null()),
    ("bg_check_rejected", pl.col("Sensor System BG Check Rejected Reason").is_not_null()),
    ("ble_device", pl.col("BLE Network Device").is_not_null()),
    ("device_update", pl.col("Device Update Event").is_not_null()),
    (
        "network_device",
        pl.col("Network Device Associated Reason").is_not_null()
        | pl.col("Network Device Disassociated Reason").is_not_null()
        | pl.col("Network Device Disconnected Reason").is_not_null(),
    ),
    ("setting_change", pl.col("Insulin Action Curve Time").is_not_null()),
    ("event_marker", pl.col("Event Marker").is_not_null()),
]
SENSOR_RULES: list[tuple[str, pl.Expr]] = [
    ("sensor_glucose", pl.col("Sensor Glucose (mg/dL)").is_not_null()),
    ("sensor_exception", pl.col("Sensor Exception").is_not_null()),
    ("sensor_day_marker", pl.col("Event Marker").is_not_null()),
]


def _classify(rules: list[tuple[str, pl.Expr]]) -> pl.Expr:
    expr = pl.lit("empty")
    for name, cond in reversed(rules):
        expr = pl.when(cond).then(pl.lit(name)).otherwise(expr)
    return expr.alias("event_type")


def _hms_to_minutes(col: str) -> pl.Expr:
    parts = pl.col(col).str.split(":")
    return (
        parts.list.get(0).cast(pl.Float64) * 60
        + parts.list.get(1).cast(pl.Float64)
        + parts.list.get(2).cast(pl.Float64) / 60
    )


def _payload_hash(df: pl.DataFrame) -> pl.Series:
    cols = [c for c in df.columns if c in TYPED_COLUMNS]
    joined = df.select(pl.concat_str([pl.col(c).fill_null("") for c in cols], separator="\x1f"))
    return pl.Series([hashlib.sha1(s.encode()).hexdigest()[:16] for s in joined.to_series()])


def _forward_order(df: pl.DataFrame) -> pl.DataFrame:
    """Events are exported newest-first; forward (true receipt) order = window asc, Index desc."""
    return (
        df.with_columns(
            pl.col("_source_file").str.extract(r"carelink_(\d{4}-\d{2}-\d{2})_to_").alias("_window"),
            pl.col("Index").cast(pl.Float64).cast(pl.Int64).alias("row_index"),
        )
        .sort(["_window", "row_index"], descending=[False, True])
        .drop("_window")
    )


def _observed_time_zones(cfg: Config) -> ObservedTimeZones | None:
    """Oura's observed phone time zones, if the Oura source has been transformed."""
    path = cfg.layers.transformed / "oura_tz_observations.parquet"
    if not path.exists():
        return None
    obs = pl.read_parquet(path)
    return ObservedTimeZones([(t, timedelta(minutes=m)) for t, m in obs.select("ts_utc", "utc_offset_min").iter_rows()])


def _convert_batch(
    pump: pl.DataFrame, sensor: pl.DataFrame, cfg: Config
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    final_offset = parse_utc_offset(cfg.carelink["final_device_clock_utc_offset"])
    resolver = LocalTimeResolver(cfg.carelink["home_timezone"])

    pump = _forward_order(pump).with_columns(
        pl.concat_str(["Date", "Time"], separator=" ").str.to_datetime(DT_FMT).alias("ts_device"),
        pl.col("New Device Time").str.to_datetime(DT_FMT, strict=False).alias("_new_ts"),
    )
    sensor = _forward_order(sensor).with_columns(
        pl.concat_str(["Date", "Time"], separator=" ").str.to_datetime(DT_FMT).alias("ts_device")
    )

    is_change = pump["New Device Time"].is_not_null().to_list()
    change_rows = pump.filter(pl.col("New Device Time").is_not_null())
    changes = [ClockChange(o, n) for o, n in zip(change_rows["ts_device"], change_rows["_new_ts"], strict=True)]
    corrections = segment_corrections(changes)

    pump_seg = pump_segments(is_change)
    fixed_ts, repaired = repair_day_spikes(sensor["ts_device"].to_list())
    sensor_seg = receipt_segments(fixed_ts, changes)
    pump = pump.with_columns(pl.Series("clock_segment", pump_seg), pl.lit(False).alias("ts_repaired"))
    sensor = sensor.with_columns(
        pl.Series("clock_segment", sensor_seg), pl.Series("ts_repaired", repaired), pl.Series("ts_device", fixed_ts)
    )

    observed = _observed_time_zones(cfg)
    zone_changed_at = zone_change_times(changes, corrections, final_offset)

    def add_time(df: pl.DataFrame) -> pl.DataFrame:
        utc, local_off, device_off, basis = [], [], [], []
        for ts, seg in zip(df["ts_device"], df["clock_segment"], strict=True):
            u = ts + corrections[seg] - final_offset
            dev = final_offset - corrections[seg]
            loc, why = resolver.offset(u, dev)
            if observed is not None and (seen := observed.resolve(u, loc, zone_changed_at[seg])) is not None:
                loc, why = seen, "oura_home" if seen == resolver.home_offset_at(u) else "oura_travel"
            utc.append(u)
            local_off.append(loc)
            device_off.append(dev)
            basis.append(why)
        return df.with_columns(
            pl.Series("ts_utc", utc, dtype=pl.Datetime("us")),
            pl.Series("utc_offset_min", [o.total_seconds() / 60 for o in local_off]),
            pl.Series("device_offset_min", [o.total_seconds() / 60 for o in device_off]),
            pl.Series("tz_basis", basis),
        ).with_columns((pl.col("ts_utc") + pl.duration(minutes=pl.col("utc_offset_min"))).alias("ts_local"))

    pump, sensor = add_time(pump), add_time(sensor)
    pump = pump.with_columns(pl.int_range(pl.len()).alias("seq"))
    sensor = sensor.with_columns(pl.int_range(pl.len()).alias("seq"))

    clock = (
        pump.filter(pl.col("New Device Time").is_not_null())
        .select(
            pl.col("_batch_id").alias("batch_id"),
            "seq",
            pl.col("ts_device").alias("ts_device_old"),
            pl.col("_new_ts").alias("ts_device_new"),
            ((pl.col("_new_ts") - pl.col("ts_device")).dt.total_seconds() / 60).alias("delta_min"),
            "ts_utc",
            pl.col("device_offset_min").alias("device_offset_min_before"),
        )
        .with_columns(
            (pl.col("device_offset_min_before") + pl.col("delta_min")).round(2).alias("device_offset_min_after")
        )
    )
    return pump.drop("_new_ts"), sensor, clock


def _type_payload(df: pl.DataFrame) -> pl.DataFrame:
    exprs = []
    for raw, (name, dtype) in TYPED_COLUMNS.items():
        if dtype == pl.Int64:
            exprs.append(pl.col(raw).cast(pl.Float64, strict=False).cast(pl.Int64).alias(name))
        elif dtype == pl.Float64:
            exprs.append(pl.col(raw).cast(pl.Float64, strict=False).alias(name))
        else:
            exprs.append(pl.col(raw).alias(name))
    typed = df.with_columns(exprs).with_columns(
        _hms_to_minutes("Temp Basal Duration (h:mm:ss)").alias("temp_basal_duration_min"),
        _hms_to_minutes("Bolus Duration (h:mm:ss)").alias("bolus_duration_min"),
        (pl.col("rewind") == "Rewind").alias("rewind"),
    )
    return typed


def build(cfg: Config) -> dict:
    raw = pl.read_parquet(cfg.layers.raw / "carelink_events.parquet")
    events, auto_insulin, clocks = [], [], []
    for batch_id in raw["_batch_id"].unique().sort():
        b = raw.filter(pl.col("_batch_id") == batch_id)
        pump = b.filter(pl.col("_section") == "pump").with_columns(_classify(PUMP_RULES))
        sensor = b.filter(pl.col("_section") == "sensor").with_columns(_classify(SENSOR_RULES))
        pump, sensor, clock = _convert_batch(pump, sensor, cfg)
        events += [pump, sensor]
        clocks.append(clock)
        auto_insulin.append(b.filter(pl.col("_section") == "pump_aggregated_auto_insulin"))

    ev = pl.concat(events, how="diagonal_relaxed")
    ev = ev.with_columns(_payload_hash(ev).alias("payload_hash"))
    ev = _type_payload(ev)

    start_device = datetime.fromisoformat(cfg.carelink["instinct_era_start_device_local"])
    anchor = ev.filter((pl.col("_section") == "pump") & (pl.col("ts_device") == start_device))
    if anchor.is_empty():
        raise ValueError(f"instinct_era_start_device_local {start_device} matches no pump event")
    era_start_utc = anchor["ts_utc"].min()

    keep_meta = [
        "event_id",
        "batch_id",
        "source_file",
        "source_line",
        "file_sha256",
        "section",
        "row_index",
        "seq",
        "event_type",
        "ts_device",
        "ts_utc",
        "ts_local",
        "date_local",
        "utc_offset_min",
        "device_offset_min",
        "tz_basis",
        "clock_segment",
        "ts_repaired",
        "cgm_era",
        "payload_hash",
    ]
    typed_names = [n for n, _ in TYPED_COLUMNS.values()] + ["temp_basal_duration_min", "bolus_duration_min"]

    ev = ev.with_columns(
        pl.col("ts_local").dt.date().alias("date_local"),
        pl.when(pl.col("ts_utc") >= era_start_utc)
        .then(pl.lit("instinct"))
        .otherwise(pl.lit("pre_instinct"))
        .alias("cgm_era"),
        pl.concat_str(
            [pl.col("_section"), pl.col("event_type"), pl.col("ts_utc").cast(pl.Utf8), pl.col("payload_hash")],
            separator="|",
        )
        .map_elements(lambda s: hashlib.sha1(s.encode()).hexdigest()[:20], return_dtype=pl.Utf8)
        .alias("event_id"),
    ).rename(
        {
            "_batch_id": "batch_id",
            "_source_file": "source_file",
            "_source_line": "source_line",
            "_file_sha256": "file_sha256",
            "_section": "section",
        }
    )

    n_before = ev.height
    # Same event in the same or an overlapping later export: keep the latest batch's copy.
    ev = (
        ev.sort(["batch_id", "section", "seq"], descending=[True, False, False])
        .unique(subset=["event_id"], keep="first", maintain_order=True)
        .sort(["section", "batch_id", "seq"])
    )
    events_out = ev.select(keep_meta + typed_names)

    # One row per device per day. A multi-pump export (e.g. after a pump replacement) lists every pump, with
    # empty rows for the one not in use: drop empties, sum devices within a file (both pumps can deliver on the
    # swap day), then across overlapping exports keep the latest batch's figure.
    ai = (
        pl.concat(auto_insulin)
        .select(
            pl.col("Date").str.to_date("%Y/%m/%d").alias("date_device"),
            pl.col("Bolus Volume Selected (U)").cast(pl.Float64).alias("auto_insulin_selected_u"),
            pl.col("Bolus Volume Delivered (U)").cast(pl.Float64).alias("auto_insulin_delivered_u"),
            pl.col("Bolus Source").alias("bolus_source"),
            pl.col("_batch_id").alias("batch_id"),
            pl.col("_source_file").alias("source_file"),
            pl.col("_source_line").alias("source_line"),
        )
        .filter(pl.col("auto_insulin_delivered_u").is_not_null())
        .group_by(["batch_id", "source_file", "date_device"])
        .agg(
            pl.col("auto_insulin_selected_u").sum(),
            pl.col("auto_insulin_delivered_u").sum(),
            pl.col("bolus_source").first(),
            pl.col("source_line").min(),
        )
        .sort(["batch_id", "source_file", "date_device"], descending=[True, True, False])
        .unique(subset=["date_device"], keep="first")
        .sort("date_device")
        .select(
            "date_device",
            "auto_insulin_selected_u",
            "auto_insulin_delivered_u",
            "bolus_source",
            "batch_id",
            "source_file",
            "source_line",
        )
    )

    out = cfg.layers.transformed
    out.mkdir(parents=True, exist_ok=True)
    events_out.write_parquet(out / "carelink_events.parquet")
    ai.write_parquet(out / "carelink_daily_auto_insulin.parquet")
    # Overlapping exports reconstruct the same clock changes; like events, the latest batch's copy wins.
    clock_df = (
        pl.concat(clocks)
        .sort(["batch_id", "ts_utc"], descending=[True, False])
        .unique(subset=["ts_utc", "delta_min"], keep="first")
        .sort("ts_utc")
    )
    clock_df.write_parquet(out / "carelink_clock_changes.parquet")
    return {
        "events": events_out.height,
        "duplicates_removed": n_before - events_out.height,
        "daily_auto_insulin_days": ai.height,
        "clock_changes": clock_df.height,
        "era_start_utc": str(era_start_utc),
    }
