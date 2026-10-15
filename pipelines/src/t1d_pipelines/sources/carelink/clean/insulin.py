"""Insulin objects: boluses (assembled from their event fragments), bolus-wizard calcs, meals."""

from __future__ import annotations

from datetime import timedelta

import polars as pl

LINEAGE = ["batch_id", "source_file", "source_line"]
CANCEL_MATCH_WINDOW = timedelta(seconds=5)


def boluses(events: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Assemble one Bolus from its fragments: programmed -> (canceled) -> delivered.

    Fragments share a 'Bolus Number', but numbers are reused and many cancel records don't
    belong to any live bolus (they cancel a wizard screen). A cancel is attached only if it
    falls inside a bolus's delivery window (programmed .. delivered + 5 s).
    Returns (boluses, number of unattached cancel records).
    """
    frags = events.filter(pl.col("event_type").is_in(["bolus_programmed", "bolus_delivered", "bolus_canceled"])).sort(
        ["batch_id", "seq"]
    )
    open_: dict[int, dict] = {}
    done: list[dict] = []
    last_done: dict[int, dict] = {}
    stray_cancels = 0
    for r in frags.iter_rows(named=True):
        n, kind = r["bolus_number"], r["event_type"]
        if kind == "bolus_programmed":
            if n in open_:
                done.append(open_.pop(n) | {"completion": "no_delivery_record"})
            open_[n] = {
                "bolus_id": "bolus_" + r["event_id"],
                "bolus_number": n,
                "programmed_utc": r["ts_utc"],
                "programmed_local": r["ts_local"],
                "date_local": r["date_local"],
                "units_programmed": r["bolus_selected_u"],
                "bolus_type": r["bolus_type"],
                "bolus_source": r["bolus_source"],
                "was_canceled": False,
                "cancel_reason": None,
                "batch_id": r["batch_id"],
                "source_file": r["source_file"],
                "source_line": r["source_line"],
            }
        elif kind == "bolus_delivered":
            b = open_.pop(n, None)
            if b is None:  # programmed fragment missing (e.g. before the export window)
                b = {
                    "bolus_id": "bolus_" + r["event_id"],
                    "bolus_number": n,
                    "programmed_utc": None,
                    "programmed_local": None,
                    "date_local": r["date_local"],
                    "units_programmed": r["bolus_selected_u"],
                    "bolus_type": r["bolus_type"],
                    "bolus_source": r["bolus_source"],
                    "was_canceled": False,
                    "cancel_reason": None,
                    "batch_id": r["batch_id"],
                    "source_file": r["source_file"],
                    "source_line": r["source_line"],
                    "completion": "no_programmed_record",
                }
            b.update(delivered_utc=r["ts_utc"], units_delivered=r["bolus_delivered_u"])
            b.setdefault("completion", "delivered")
            done.append(b)
            last_done[n] = b
        else:  # canceled
            if n in open_:
                open_[n].update(was_canceled=True, cancel_reason=r["bolus_cancel_reason"])
            elif n in last_done and abs(r["ts_utc"] - last_done[n]["delivered_utc"]) <= CANCEL_MATCH_WINDOW:
                last_done[n].update(was_canceled=True, cancel_reason=r["bolus_cancel_reason"])
            else:
                stray_cancels += 1
    done += [b | {"completion": "no_delivery_record"} for b in open_.values()]

    schema = {
        "bolus_id": pl.Utf8,
        "bolus_number": pl.Int64,
        "programmed_utc": pl.Datetime("us"),
        "programmed_local": pl.Datetime("us"),
        "date_local": pl.Date,
        "units_programmed": pl.Float64,
        "bolus_type": pl.Utf8,
        "bolus_source": pl.Utf8,
        "was_canceled": pl.Boolean,
        "cancel_reason": pl.Utf8,
        "batch_id": pl.Utf8,
        "source_file": pl.Utf8,
        "source_line": pl.Int64,
        "completion": pl.Utf8,
        "delivered_utc": pl.Datetime("us"),
        "units_delivered": pl.Float64,
    }
    df = pl.DataFrame(done, schema=schema)
    df = df.with_columns(
        pl.coalesce("programmed_utc", "delivered_utc").alias("start_utc"),
        ((pl.col("delivered_utc") - pl.col("programmed_utc")).dt.total_seconds() / 60)
        .round(2)
        .alias("delivery_minutes"),
        pl.when(pl.col("bolus_source").str.starts_with("CLOSED_LOOP"))
        .then(pl.lit("smartguard"))
        .when(pl.col("bolus_source").is_not_null())
        .then(pl.lit("manual"))
        .alias("pump_mode"),
        pl.when(pl.col("bolus_source").str.contains("FOOD"))
        .then(pl.lit("meal_and_correction"))
        .when(pl.col("bolus_source") == "CLOSED_LOOP_BG_CORRECTION")
        .then(pl.lit("correction"))
        .otherwise(pl.lit("wizard_manual_mode"))
        .alias("bolus_kind"),
        (pl.col("units_delivered") < pl.col("units_programmed") - 1e-6).alias("is_partial"),
    ).sort("start_utc")
    return df, stray_cancels


def wizard_calcs(events: pl.DataFrame, bolus_df: pl.DataFrame) -> pl.DataFrame:
    """Bolus Wizard calculations, enriched with their 'detail' row and linked to the bolus they produced."""
    w = events.filter(pl.col("event_type") == "bolus_wizard")
    detail = (
        events.filter(pl.col("event_type") == "bolus_wizard_detail")
        .select("ts_utc", "bwz_unabsorbed_insulin_u", "bwz_final_estimate_u")
        .unique(subset=["ts_utc"], keep="first")
    )
    w = (
        w.drop("bwz_unabsorbed_insulin_u", "bwz_final_estimate_u")
        .join(detail, on="ts_utc", how="left")
        .select(
            pl.col("event_id").alias("wizard_id"),
            "ts_utc",
            "ts_local",
            "date_local",
            pl.col("bwz_carbs_g").alias("carbs_g"),
            pl.col("bwz_bg_input_mgdl").alias("bg_input_mgdl"),
            pl.col("bwz_carb_ratio_g_per_u").alias("carb_ratio_g_per_u"),
            pl.col("bwz_isf_mgdl_per_u").alias("isf_mgdl_per_u"),
            pl.col("bwz_target_low_mgdl").alias("target_low_mgdl"),
            pl.col("bwz_target_high_mgdl").alias("target_high_mgdl"),
            pl.col("bwz_food_estimate_u").alias("food_estimate_u"),
            pl.col("bwz_correction_estimate_u").alias("correction_estimate_u"),
            pl.col("bwz_active_insulin_u").alias("active_insulin_u"),
            pl.col("bwz_estimate_u").alias("estimate_u"),
            pl.col("bwz_final_estimate_u").alias("final_estimate_u"),
            pl.col("bwz_unabsorbed_insulin_u").alias("unabsorbed_insulin_u"),
            pl.col("bwz_status").alias("status"),
            *LINEAGE,
        )
        .sort("ts_utc")
    )
    targets = (
        bolus_df.filter(pl.col("programmed_utc").is_not_null())
        .select("bolus_id", pl.col("programmed_utc").alias("_t"))
        .sort("_t")
    )
    delivered = (
        w.filter(pl.col("status") == "Delivered")
        .join_asof(targets, left_on="ts_utc", right_on="_t", strategy="forward", tolerance="30s")
        .drop("_t")
    )
    return w.join(delivered.select("wizard_id", "bolus_id"), on="wizard_id", how="left")


def meals(
    wizard: pl.DataFrame, bolus_df: pl.DataFrame, g: pl.DataFrame, minutes: int, window_hours: int, thresholds: dict
) -> pl.DataFrame:
    """A Meal is a wizard entry with carbs > 0, plus its glucose response over the next few hours.

    Response features come from the 5-min grid. Confounders are flagged instead of removed:
    another meal inside the window, or poor CGM coverage.
    """
    m = (
        wizard.filter(pl.col("carbs_g") > 0)
        .join(bolus_df.select("bolus_id", "units_delivered", "delivery_minutes"), on="bolus_id", how="left")
        .select(
            ("meal_" + pl.col("wizard_id")).alias("meal_id"),
            "wizard_id",
            "bolus_id",
            "ts_utc",
            "ts_local",
            "date_local",
            "carbs_g",
            "carb_ratio_g_per_u",
            "bg_input_mgdl",
            "active_insulin_u",
            "food_estimate_u",
            "correction_estimate_u",
            "estimate_u",
            pl.col("units_delivered").alias("bolus_units_delivered"),
            "status",
            *LINEAGE,
        )
        .sort("ts_utc")
        .with_columns(
            ((pl.col("ts_utc").shift(-1) - pl.col("ts_utc")).dt.total_seconds() / 60)
            .round(1)
            .alias("minutes_to_next_meal")
        )
    )
    n_after = window_hours * 60 // minutes
    offsets = pl.DataFrame({"k": list(range(-3, n_after + 1))})
    probe = (
        m.select("meal_id", "ts_utc")
        .join(offsets, how="cross")
        .with_columns(
            (pl.col("ts_utc").dt.truncate(f"{minutes}m") + pl.duration(minutes=pl.col("k") * minutes)).alias(
                "bin_start_utc"
            )
        )
        .join(
            g.select("bin_start_utc", "sg_mgdl", "sensor_id", "sensor_age_hours", "set_id", "set_age_hours"),
            on="bin_start_utc",
            how="left",
        )
    )
    lo, hi = thresholds["low"], thresholds["high"]
    after = pl.col("k") >= 0
    per_bins_3h = 180 // minutes

    def sg_near(k: int, name: str) -> pl.Expr:
        """SG at grid offset k, falling back to the neighbouring bin (earlier first) if k is a gap."""
        at = lambda j: pl.col("sg_mgdl").filter(pl.col("k") == j).first()  # noqa: E731
        return pl.coalesce(at(k), at(k - 1), at(k + 1)).alias(name)

    feats = probe.group_by("meal_id").agg(
        sg_near(0, "sg_at_meal_mgdl"),
        sg_near(-3, "sg_15min_before_mgdl"),
        pl.col("sg_mgdl").filter(after & (pl.col("k") <= per_bins_3h)).max().alias("peak_sg_0_3h_mgdl"),
        (
            pl.col("k")
            .filter(after & (pl.col("k") <= per_bins_3h))
            .get(pl.col("sg_mgdl").filter(after & (pl.col("k") <= per_bins_3h)).arg_max())
            * minutes
        ).alias("minutes_to_peak"),
        sg_near(120 // minutes, "sg_2h_mgdl"),
        sg_near(180 // minutes, "sg_3h_mgdl"),
        sg_near(n_after, "sg_end_window_mgdl"),
        pl.col("sg_mgdl").filter(after).min().alias("nadir_sg_window_mgdl"),
        (pl.col("sg_mgdl").filter(after) < lo).any().alias("low_in_window"),
        ((pl.col("sg_mgdl").filter(after) >= lo) & (pl.col("sg_mgdl").filter(after) <= hi)).mean().alias("tir_window"),
        pl.col("sg_mgdl").filter(after).is_not_null().mean().alias("cgm_coverage_window"),
        pl.col("sensor_id").filter(pl.col("k") == 0).first(),
        pl.col("sensor_age_hours").filter(pl.col("k") == 0).first(),
        pl.col("set_id").filter(pl.col("k") == 0).first(),
        pl.col("set_age_hours").filter(pl.col("k") == 0).first(),
    )
    return (
        m.join(feats, on="meal_id", how="left")
        .with_columns(
            (pl.col("peak_sg_0_3h_mgdl") - pl.col("sg_at_meal_mgdl")).alias("rise_to_peak_mgdl"),
            (pl.col("sg_3h_mgdl") - pl.col("sg_at_meal_mgdl")).alias("delta_3h_mgdl"),
            ((pl.col("sg_at_meal_mgdl") - pl.col("sg_15min_before_mgdl")) / 15)
            .round(2)
            .alias("trend_at_meal_mgdl_per_min"),
            (pl.col("carbs_g") / pl.col("bolus_units_delivered")).round(2).alias("effective_g_per_u"),
            (pl.col("minutes_to_next_meal") < window_hours * 60).fill_null(False).alias("next_meal_in_window"),
            pl.col("tir_window").round(3),
            pl.col("cgm_coverage_window").round(3),
            pl.col("ts_local").dt.hour().alias("hour_local"),
            pl.when(pl.col("ts_local").dt.hour().is_between(4, 10))
            .then(pl.lit("breakfast"))
            .when(pl.col("ts_local").dt.hour().is_between(11, 15))
            .then(pl.lit("lunch"))
            .when(pl.col("ts_local").dt.hour().is_between(16, 21))
            .then(pl.lit("dinner"))
            .otherwise(pl.lit("late_night"))
            .alias("meal_slot"),
        )
        .sort("ts_utc")
    )
