"""Oura transformed layer: typed, deduplicated (latest pull wins), UTC-normalised tables.

    transformed/oura_daily.parquet            one row per day: sleep / readiness / activity / stress /
                                              resilience / SpO2 / cardio-age / VO2max fields
    transformed/oura_sleep.parquet            one row per sleep session (main night, naps)
    transformed/oura_workout.parquet          one row per workout
    transformed/oura_heartrate.parquet        one row per HR sample (UTC)
    transformed/oura_tz_observations.parquet  (utc instant, UTC offset) seen on sleep / workout timestamps:
                                              the phone's real time zone, used to correct pump-clock local time

Durations are converted from seconds to minutes; every datetime gets `*_utc` (naive UTC) plus the
observed `*_offset_min`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import polars as pl
from t1d_core.settings import Config


def parse_ts(text: str | None) -> tuple[datetime | None, int | None]:
    """'2026-08-12T23:40:00.000+02:00' -> (naive UTC datetime, offset minutes)."""
    if not text:
        return None, None
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    offset = dt.utcoffset()
    return dt.astimezone(UTC).replace(tzinfo=None), int(offset.total_seconds() // 60) if offset is not None else None


def _latest(raw: pl.DataFrame, endpoint: str) -> list[dict]:
    rows = raw.filter(pl.col("endpoint") == endpoint).sort("pull_id").unique(subset=["id"], keep="last")
    return [json.loads(d) for d in rows["document"]]


def _minutes(seconds) -> float | None:
    return None if seconds is None else round(seconds / 60, 1)


def _daily(raw: pl.DataFrame) -> pl.DataFrame:
    by_day: dict[str, dict] = {}

    def put(day: str, values: dict) -> None:
        by_day.setdefault(day, {"date_local": day}).update(values)

    for d in sorted(_latest(raw, "daily_sleep"), key=lambda x: x.get("timestamp") or ""):
        c = d.get("contributors") or {}
        put(d["day"], {"sleep_score": d.get("score")} | {f"sleep_c_{k}": v for k, v in c.items()})
    for d in sorted(_latest(raw, "daily_readiness"), key=lambda x: x.get("timestamp") or ""):
        c = d.get("contributors") or {}
        put(
            d["day"],
            {
                "readiness_score": d.get("score"),
                "temperature_deviation": d.get("temperature_deviation"),
                "temperature_trend_deviation": d.get("temperature_trend_deviation"),
            }
            | {f"readiness_c_{k}": v for k, v in c.items()},
        )
    for d in sorted(_latest(raw, "daily_activity"), key=lambda x: x.get("timestamp") or ""):
        put(
            d["day"],
            {
                "activity_score": d.get("score"),
                "steps": d.get("steps"),
                "active_calories": d.get("active_calories"),
                "total_calories": d.get("total_calories"),
                "high_activity_min": _minutes(d.get("high_activity_time")),
                "medium_activity_min": _minutes(d.get("medium_activity_time")),
                "low_activity_min": _minutes(d.get("low_activity_time")),
                "sedentary_min": _minutes(d.get("sedentary_time")),
                "non_wear_min": _minutes(d.get("non_wear_time")),
                "walking_distance_m": d.get("equivalent_walking_distance"),
            },
        )
    for d in _latest(raw, "daily_stress"):
        put(
            d["day"],
            {
                "stress_high_min": _minutes(d.get("stress_high")),
                "recovery_high_min": _minutes(d.get("recovery_high")),
                "stress_summary": d.get("day_summary"),
            },
        )
    for d in _latest(raw, "daily_resilience"):
        put(d["day"], {"resilience_level": d.get("level")})
    for d in _latest(raw, "daily_spo2"):
        spo2 = d.get("spo2_percentage") or {}
        put(
            d["day"],
            {"spo2_pct": spo2.get("average"), "breathing_disturbance_index": d.get("breathing_disturbance_index")},
        )
    for d in _latest(raw, "daily_cardiovascular_age"):
        put(d["day"], {"vascular_age": d.get("vascular_age")})
    for d in _latest(raw, "vO2_max"):
        put(d["day"], {"vo2_max": d.get("vo2_max")})
    if not by_day:
        return pl.DataFrame(schema={"date_local": pl.Date})
    df = pl.DataFrame(list(by_day.values()), infer_schema_length=None)
    return df.with_columns(pl.col("date_local").str.to_date()).sort("date_local")


SLEEP_SCHEMA = {
    "sleep_id": pl.Utf8, "date_local": pl.Utf8, "sleep_type": pl.Utf8,
    "bedtime_start_utc": pl.Datetime("us"), "bedtime_end_utc": pl.Datetime("us"), "utc_offset_min": pl.Int64,
    "time_in_bed_min": pl.Float64, "total_sleep_min": pl.Float64, "deep_sleep_min": pl.Float64,
    "rem_sleep_min": pl.Float64, "light_sleep_min": pl.Float64, "awake_min": pl.Float64, "latency_min": pl.Float64,
    "efficiency": pl.Float64, "average_hrv": pl.Float64, "average_heart_rate": pl.Float64,
    "lowest_heart_rate": pl.Float64, "average_breath": pl.Float64, "restless_periods": pl.Float64,
}  # fmt: skip


def _sleep(raw: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for d in _latest(raw, "sleep"):
        start, off = parse_ts(d.get("bedtime_start"))
        end, _ = parse_ts(d.get("bedtime_end"))
        rows.append(
            {
                "sleep_id": d["id"], "date_local": d.get("day"), "sleep_type": d.get("type"),
                "bedtime_start_utc": start, "bedtime_end_utc": end, "utc_offset_min": off,
                "time_in_bed_min": _minutes(d.get("time_in_bed")), "total_sleep_min": _minutes(d.get("total_sleep_duration")),
                "deep_sleep_min": _minutes(d.get("deep_sleep_duration")), "rem_sleep_min": _minutes(d.get("rem_sleep_duration")),
                "light_sleep_min": _minutes(d.get("light_sleep_duration")), "awake_min": _minutes(d.get("awake_time")),
                "latency_min": _minutes(d.get("latency")), "efficiency": d.get("efficiency"),
                "average_hrv": d.get("average_hrv"), "average_heart_rate": d.get("average_heart_rate"),
                "lowest_heart_rate": d.get("lowest_heart_rate"), "average_breath": d.get("average_breath"),
                "restless_periods": d.get("restless_periods"),
            }
        )  # fmt: skip
    return (
        pl.DataFrame(rows, schema=SLEEP_SCHEMA)
        .with_columns(pl.col("date_local").str.to_date())
        .sort("bedtime_start_utc")
    )


def _workouts(raw: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for d in _latest(raw, "workout"):
        start, off = parse_ts(d.get("start_datetime"))
        end, _ = parse_ts(d.get("end_datetime"))
        rows.append(
            {
                "workout_id": d["id"], "date_local": d.get("day"), "activity": d.get("activity"),
                "intensity": d.get("intensity"), "source": d.get("source"), "label": d.get("label"),
                "start_utc": start, "end_utc": end, "utc_offset_min": off,
                "calories": d.get("calories"), "distance_m": d.get("distance"),
            }
        )  # fmt: skip
    schema = {
        "workout_id": pl.Utf8, "date_local": pl.Utf8, "activity": pl.Utf8, "intensity": pl.Utf8, "source": pl.Utf8,
        "label": pl.Utf8, "start_utc": pl.Datetime("us"), "end_utc": pl.Datetime("us"), "utc_offset_min": pl.Int64,
        "calories": pl.Float64, "distance_m": pl.Float64,
    }  # fmt: skip
    return pl.DataFrame(rows, schema=schema).with_columns(pl.col("date_local").str.to_date()).sort("start_utc")


def _heartrate(cfg: Config) -> pl.DataFrame:
    hr = pl.read_parquet(cfg.layers.raw / "oura_heartrate.parquet")
    return (
        hr.sort("pull_id")
        .unique(subset=["timestamp", "source"], keep="last")
        .with_columns(
            pl.col("timestamp").str.to_datetime(time_zone="UTC").dt.replace_time_zone(None).dt.cast_time_unit("us")
        )
        .select(pl.col("timestamp").alias("ts_utc"), "bpm", "source")
        .sort("ts_utc")
    )


def tz_observations(sleep: pl.DataFrame, workouts: pl.DataFrame) -> pl.DataFrame:
    """Instants where Oura saw the phone's real UTC offset (start and end of every sleep and workout)."""
    parts = []
    for df, start, end, origin in (
        (sleep, "bedtime_start_utc", "bedtime_end_utc", "sleep"),
        (workouts, "start_utc", "end_utc", "workout"),
    ):
        for col, edge in ((start, "start"), (end, "end")):
            parts.append(
                df.select(pl.col(col).alias("ts_utc"), "utc_offset_min", pl.lit(f"{origin}_{edge}").alias("origin"))
            )
    obs = pl.concat(parts).drop_nulls()
    return obs.sort("ts_utc").unique(subset=["ts_utc"], keep="first", maintain_order=True)


def build(cfg: Config) -> dict:
    raw = pl.read_parquet(cfg.layers.raw / "oura_documents.parquet")
    daily, sleep, workouts = _daily(raw), _sleep(raw), _workouts(raw)
    hr = _heartrate(cfg)
    obs = tz_observations(sleep, workouts)
    out = cfg.layers.transformed
    out.mkdir(parents=True, exist_ok=True)
    for name, df in {
        "oura_daily": daily, "oura_sleep": sleep, "oura_workout": workouts,
        "oura_heartrate": hr, "oura_tz_observations": obs,
    }.items():  # fmt: skip
        df.write_parquet(out / f"{name}.parquet")
    return {"days": daily.height, "sleep_sessions": sleep.height, "workouts": workouts.height,
            "heartrate_samples": hr.height, "tz_observations": obs.height}  # fmt: skip
