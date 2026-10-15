"""Oura clean layer: ontology objects, joined with CareLink glucose / insulin.

    clean/oura_day.parquet          OuraDay: daily scores + the main night, one per Oura day
    clean/sleep_session.parquet     SleepSession: every sleep, with glucose / insulin while asleep
    clean/workout.parquet           Workout: every workout, with glucose before, during and 12 h after
    clean/heart_rate_5min.parquet   HeartRate5Min: mean / max bpm per 5-min bin, aligned to Glucose5Min

Scope: every Oura day from the start of the analysis era (the first `Day`) onwards, including days after
the latest CareLink export, so recovery stays current even when pump data lags. Links to `Day` and
`Glucose5Min` are declared `required: false` for exactly that reason; glucose features are null there.
Local times use Oura's own observed UTC offset. Runs after the CareLink clean step; with no Oura
data it writes empty, correctly typed tables so the ontology still validates.
"""

from __future__ import annotations

import duckdb
import polars as pl
from t1d_core.settings import Config

LOW, HIGH = 70, 180


def _empty_if_missing(cfg: Config, name: str) -> pl.DataFrame | None:
    path = cfg.layers.transformed / f"{name}.parquet"
    return pl.read_parquet(path) if path.exists() else None


def build(cfg: Config) -> dict:
    t, c = cfg.layers.transformed, cfg.layers.clean
    con = duckdb.connect()
    for name in ("day", "glucose_5min", "glycemic_excursion", "bolus", "meal", "pump_suspension"):
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{c / f'{name}.parquet'}')")
    has_oura = (t / "oura_sleep.parquet").exists()
    for name in ("oura_daily", "oura_sleep", "oura_workout", "oura_heartrate"):
        src = t / f"{name}.parquet"
        if has_oura:
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{src}')")
    if not has_oura:
        con.execute("CREATE TABLE oura_daily (date_local DATE)")
        con.execute(
            """CREATE TABLE oura_sleep (sleep_id VARCHAR, date_local DATE, sleep_type VARCHAR, bedtime_start_utc TIMESTAMP,
               bedtime_end_utc TIMESTAMP, utc_offset_min BIGINT, time_in_bed_min DOUBLE, total_sleep_min DOUBLE,
               deep_sleep_min DOUBLE, rem_sleep_min DOUBLE, light_sleep_min DOUBLE, awake_min DOUBLE, latency_min DOUBLE,
               efficiency DOUBLE, average_hrv DOUBLE, average_heart_rate DOUBLE, lowest_heart_rate DOUBLE,
               average_breath DOUBLE, restless_periods DOUBLE)"""
        )
        con.execute(
            """CREATE TABLE oura_workout (workout_id VARCHAR, date_local DATE, activity VARCHAR, intensity VARCHAR,
               source VARCHAR, label VARCHAR, start_utc TIMESTAMP, end_utc TIMESTAMP, utc_offset_min BIGINT,
               calories DOUBLE, distance_m DOUBLE)"""
        )
        con.execute("CREATE TABLE oura_heartrate (ts_utc TIMESTAMP, bpm BIGINT, source VARCHAR)")

    sleep = con.execute(
        f"""
        WITH s AS (SELECT * FROM oura_sleep WHERE date_local >= (SELECT min(date_local) FROM day))
        SELECT s.sleep_id, s.date_local, s.sleep_type,
               s.bedtime_start_utc, s.bedtime_end_utc,
               s.bedtime_start_utc + to_minutes(s.utc_offset_min) AS bedtime_start_local,
               s.bedtime_end_utc + to_minutes(s.utc_offset_min) AS bedtime_end_local,
               s.utc_offset_min, s.time_in_bed_min, s.total_sleep_min, s.deep_sleep_min, s.rem_sleep_min,
               s.light_sleep_min, s.awake_min, s.latency_min, s.efficiency, s.average_hrv, s.average_heart_rate,
               s.lowest_heart_rate, s.average_breath, s.restless_periods,
               g.mean_sg_mgdl, g.min_sg_mgdl, g.max_sg_mgdl, g.tir, g.tbr, g.cgm_coverage,
               (SELECT sg_mgdl FROM glucose_5min x WHERE x.has_data AND x.bin_start_utc <= s.bedtime_start_utc
                ORDER BY x.bin_start_utc DESC LIMIT 1) AS sg_at_bedtime_mgdl,
               (SELECT sg_mgdl FROM glucose_5min x WHERE x.has_data AND x.bin_start_utc <= s.bedtime_end_utc
                ORDER BY x.bin_start_utc DESC LIMIT 1) AS sg_at_wake_mgdl,
               (SELECT count(*) FROM glycemic_excursion e WHERE e.kind = 'hypo'
                AND e.start_utc >= s.bedtime_start_utc AND e.start_utc < s.bedtime_end_utc) AS n_hypo,
               (SELECT coalesce(sum(units_delivered), 0) FROM bolus b
                WHERE b.start_utc >= s.bedtime_start_utc - INTERVAL 3 HOUR AND b.start_utc < s.bedtime_start_utc)
                AS bolus_u_3h_before_bed
        FROM s LEFT JOIN (
            SELECT s2.sleep_id, avg(g.sg_mgdl) AS mean_sg_mgdl, min(g.sg_mgdl) AS min_sg_mgdl, max(g.sg_mgdl) AS max_sg_mgdl,
                   avg((g.sg_mgdl BETWEEN {LOW} AND {HIGH})::INT) FILTER (WHERE g.has_data) AS tir,
                   avg((g.sg_mgdl < {LOW})::INT) FILTER (WHERE g.has_data) AS tbr,
                   avg(g.has_data::INT) AS cgm_coverage
            FROM s s2 JOIN glucose_5min g ON g.bin_start_utc >= s2.bedtime_start_utc AND g.bin_start_utc < s2.bedtime_end_utc
            GROUP BY 1) g USING (sleep_id)
        ORDER BY s.bedtime_start_utc"""
    ).pl()

    workouts = con.execute(
        """
        WITH w AS (SELECT * FROM oura_workout WHERE date_local >= (SELECT min(date_local) FROM day))
        SELECT w.workout_id, w.date_local, w.activity, w.intensity, w.source, w.label,
               w.start_utc, w.end_utc, w.start_utc + to_minutes(w.utc_offset_min) AS start_local,
               w.end_utc + to_minutes(w.utc_offset_min) AS end_local, w.utc_offset_min,
               date_diff('second', w.start_utc, w.end_utc) / 60.0 AS duration_min, w.calories, w.distance_m,
               (SELECT sg_mgdl FROM glucose_5min x WHERE x.has_data AND x.bin_start_utc <= w.start_utc
                ORDER BY x.bin_start_utc DESC LIMIT 1) AS sg_at_start_mgdl,
               (SELECT min(sg_mgdl) FROM glucose_5min x WHERE x.bin_start_utc >= w.start_utc AND x.bin_start_utc < w.end_utc)
                AS min_sg_during_mgdl,
               (SELECT sg_mgdl FROM glucose_5min x WHERE x.has_data AND x.bin_start_utc <= w.end_utc
                ORDER BY x.bin_start_utc DESC LIMIT 1) AS sg_at_end_mgdl,
               (SELECT min(sg_mgdl) FROM glucose_5min x WHERE x.bin_start_utc >= w.end_utc
                AND x.bin_start_utc < w.end_utc + INTERVAL 12 HOUR) AS min_sg_12h_after_mgdl,
               (SELECT count(*) > 0 FROM glycemic_excursion e WHERE e.kind = 'hypo'
                AND e.start_utc >= w.start_utc AND e.start_utc < w.end_utc + INTERVAL 12 HOUR) AS low_within_12h,
               (SELECT coalesce(sum(carbs_g), 0) FROM meal m WHERE m.ts_utc >= w.start_utc - INTERVAL 2 HOUR
                AND m.ts_utc < w.start_utc) AS carbs_g_2h_before,
               (SELECT coalesce(sum(units_delivered), 0) FROM bolus b WHERE b.start_utc >= w.start_utc - INTERVAL 2 HOUR
                AND b.start_utc < w.start_utc) AS bolus_u_2h_before,
               (SELECT coalesce(sum(date_diff('second', greatest(p.start_utc, w.start_utc),
                       least(p.end_utc, w.end_utc)) / 60.0), 0)
                FROM pump_suspension p WHERE p.start_utc < w.end_utc AND p.end_utc > w.start_utc) AS suspended_min_during
        FROM w ORDER BY w.start_utc"""
    ).pl()

    hr = con.execute(
        """SELECT time_bucket(INTERVAL 5 MINUTE, h.ts_utc) AS bin_start_utc, round(avg(h.bpm), 1) AS mean_bpm,
                  max(h.bpm) AS max_bpm, count(*) AS n_samples, mode(h.source) AS source
           FROM oura_heartrate h
           WHERE h.ts_utc >= (SELECT min(bin_start_utc) FROM glucose_5min)
           GROUP BY 1 ORDER BY 1"""
    ).pl()

    con.register("sleep_clean", sleep.to_arrow())
    main_night = con.execute(
        """SELECT * EXCLUDE (rn) FROM (
             SELECT date_local, sleep_id AS main_sleep_id, bedtime_start_local, bedtime_end_local,
                    total_sleep_min, efficiency AS sleep_efficiency, average_hrv, lowest_heart_rate, average_breath,
                    mean_sg_mgdl AS overnight_mean_sg_mgdl, tir AS overnight_tir, tbr AS overnight_tbr,
                    n_hypo AS overnight_hypos,
                    row_number() OVER (PARTITION BY date_local ORDER BY (sleep_type = 'long_sleep') DESC,
                                       total_sleep_min DESC NULLS LAST) AS rn
             FROM sleep_clean) WHERE rn = 1"""
    ).pl()
    daily = con.execute("SELECT * FROM oura_daily WHERE date_local >= (SELECT min(date_local) FROM day)").pl()
    oura_day = daily.join(main_night, on="date_local", how="full", coalesce=True).sort("date_local")
    if "sleep_score" not in oura_day.columns:  # no Oura data: keep the declared columns
        oura_day = oura_day.head(0)

    c.mkdir(parents=True, exist_ok=True)
    tables = {"oura_day": oura_day, "sleep_session": sleep, "workout": workouts, "heart_rate_5min": hr}
    for name, df in tables.items():
        df.write_parquet(c / f"{name}.parquet")
    return {name: df.height for name, df in tables.items()}
