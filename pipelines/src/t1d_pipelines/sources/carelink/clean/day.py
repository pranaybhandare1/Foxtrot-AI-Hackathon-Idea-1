"""Day: the hub object every source joins to (CGM, insulin, and later Oura / Apple Health)."""

from __future__ import annotations

import polars as pl

MAX_SILENT_MIN = 8 * 60  # a day with an 8 h+ stretch of no CareLink records at all is incomplete


def days(
    g: pl.DataFrame,
    bolus_df: pl.DataFrame,
    meal_df: pl.DataFrame,
    exc: pl.DataFrame,
    alert_df: pl.DataFrame,
    susp: pl.DataFrame,
    auto_insulin: pl.DataFrame,
    events: pl.DataFrame,
    thresholds: dict,
    valid_coverage: float,
) -> pl.DataFrame:
    vl, lo, hi, vh = thresholds["very_low"], thresholds["low"], thresholds["high"], thresholds["very_high"]
    sg = pl.col("sg_mgdl")
    has = pl.col("has_data")

    cgm = g.group_by("date_local").agg(
        pl.len().alias("grid_bins"),
        has.sum().alias("bins_with_data"),
        sg.mean().round(1).alias("mean_sg_mgdl"),
        sg.std().round(1).alias("sd_sg_mgdl"),
        ((sg.filter(has) >= lo) & (sg.filter(has) <= hi)).mean().alias("tir"),
        ((sg.filter(has) >= lo) & (sg.filter(has) <= 140)).mean().alias("titr"),
        (sg.filter(has) < lo).mean().alias("tbr"),
        (sg.filter(has) < vl).mean().alias("tbr_level2"),
        (sg.filter(has) > hi).mean().alias("tar"),
        (sg.filter(has) > vh).mean().alias("tar_level2"),
        sg.filter(pl.col("bin_start_local").dt.hour() < 6).mean().round(1).alias("mean_sg_overnight_mgdl"),
        pl.col("sensor_id").drop_nulls().mode().first().alias("sensor_id"),
        pl.col("sensor_age_hours").filter(pl.col("bin_start_local").dt.hour() == 12).first().alias("_sensor_age_noon"),
        pl.col("set_id").drop_nulls().mode().first().alias("set_id"),
        pl.col("set_age_hours").filter(pl.col("bin_start_local").dt.hour() == 12).first().alias("_set_age_noon"),
    )
    ins = bolus_df.group_by("date_local").agg(
        pl.col("units_delivered").sum().alias("bolus_u"),
        pl.len().alias("n_boluses"),
        (pl.col("bolus_kind") == "correction").sum().alias("n_correction_boluses"),
        (pl.col("pump_mode") == "manual").sum().alias("n_manual_mode_boluses"),
    )
    food = meal_df.group_by("date_local").agg(pl.len().alias("n_meals"), pl.col("carbs_g").sum().alias("carbs_g"))
    ex = exc.group_by("date_local").agg(
        (pl.col("kind") == "hypo").sum().alias("n_hypo"),
        ((pl.col("kind") == "hypo") & (pl.col("level") == 2)).sum().alias("n_hypo_level2"),
        ((pl.col("kind") == "hypo") & pl.col("is_nocturnal")).sum().alias("n_hypo_nocturnal"),
        pl.col("duration_min").filter(pl.col("kind") == "hypo").sum().alias("hypo_minutes"),
        (pl.col("kind") == "hyper").sum().alias("n_hyper"),
    )
    al = alert_df.group_by("date_local").agg(
        pl.len().alias("n_alerts"),
        (pl.col("category") == "glucose_low").sum().alias("n_low_alerts"),
        (pl.col("category") == "glucose_high").sum().alias("n_high_alerts"),
        (pl.col("alert_type") == "SMARTGUARD EXIT").sum().alias("n_smartguard_exits"),
        (pl.col("alert_type") == "LOST SENSOR SIGNAL").sum().alias("n_signal_loss_alerts"),
    )
    su = susp.group_by("date_local").agg(
        pl.col("duration_min").sum().round(1).alias("suspended_minutes"), pl.len().alias("n_suspensions")
    )
    tz = events.group_by("date_local").agg(
        pl.col("utc_offset_min").mode().first().alias("utc_offset_min"),
        pl.col("tz_basis").str.ends_with("travel").any().alias("is_travel_day"),
        (pl.col("event_type") == "clock_change").sum().alias("n_clock_changes"),
    )
    auto = auto_insulin.select(
        pl.col("date_device").alias("date_local"), pl.col("auto_insulin_delivered_u").alias("auto_insulin_u")
    )

    d = cgm
    for part in (ins, food, ex, al, su, tz, auto):
        d = d.join(part, on="date_local", how="left")
    fill0 = [
        "bolus_u",
        "n_boluses",
        "n_correction_boluses",
        "n_manual_mode_boluses",
        "n_meals",
        "carbs_g",
        "n_hypo",
        "n_hypo_level2",
        "n_hypo_nocturnal",
        "hypo_minutes",
        "n_hyper",
        "n_alerts",
        "n_low_alerts",
        "n_high_alerts",
        "n_smartguard_exits",
        "n_signal_loss_alerts",
        "suspended_minutes",
        "n_suspensions",
    ]
    first, last = d["date_local"].min(), d["date_local"].max()
    # Partial = first / last day, or a day with a long stretch where CareLink recorded nothing at all (pump or
    # sensor), e.g. the hole between two exports. Daily totals on such days undercount.
    day_start = pl.col("date_local").cast(pl.Datetime("us"))
    gaps = (
        events.select("date_local", "ts_local")
        .drop_nulls()
        .sort("ts_local")
        .with_columns(day_start.alias("_d0"))
        .group_by("date_local")
        .agg(
            pl.max_horizontal(
                pl.col("ts_local").diff().dt.total_minutes().max().fill_null(0),
                (pl.col("ts_local").min() - pl.col("_d0").first()).dt.total_minutes(),
                (pl.col("_d0").first() + pl.duration(days=1) - pl.col("ts_local").max()).dt.total_minutes(),
            ).alias("_max_gap_min")
        )
    )
    d = d.join(gaps, on="date_local", how="left")
    return (
        d.with_columns(pl.col(fill0).fill_null(0))
        .with_columns(
            (pl.col("bins_with_data") / pl.col("grid_bins")).round(4).alias("cgm_coverage"),
            (pl.col("sd_sg_mgdl") / pl.col("mean_sg_mgdl") * 100).round(1).alias("cv_pct"),
            (3.31 + 0.02392 * pl.col("mean_sg_mgdl")).round(2).alias("gmi_pct"),
            pl.col("tir", "titr", "tbr", "tbr_level2", "tar", "tar_level2").round(4),
            (pl.col("bolus_u") + pl.col("auto_insulin_u")).round(2).alias("tdd_u"),
            (pl.col("_sensor_age_noon") / 24).floor().cast(pl.Int64).add(1).alias("sensor_day"),
            (pl.col("_set_age_noon") / 24).floor().cast(pl.Int64).add(1).alias("set_day"),
            (
                (pl.col("date_local") == first)
                | (pl.col("date_local") == last)
                | (pl.col("_max_gap_min").fill_null(1440) >= MAX_SILENT_MIN)
            ).alias("is_partial_day"),
            pl.col("date_local").dt.strftime("%a").alias("weekday"),
        )
        .with_columns(
            (pl.col("auto_insulin_u") / pl.col("tdd_u")).round(4).alias("auto_insulin_share"),
            ((pl.col("cgm_coverage") >= valid_coverage) & ~pl.col("is_partial_day")).alias("is_valid_cgm_day"),
        )
        .drop("_sensor_age_noon", "_set_age_noon", "_max_gap_min")
        .sort("date_local")
    )
