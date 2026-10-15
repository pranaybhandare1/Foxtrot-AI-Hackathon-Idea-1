# Pranay360 data

The backend data product behind Pranay360: one person's type 1 diabetes data (Medtronic MiniMed 780G pump +
Abbott Instinct CGM via CareLink) joined with Oura ring sleep, readiness and activity, modelled as an
**ontology** (object types, properties, links and actions, Palantir-Foundry style) over a clean,
validated data layer. Starting point for building models, agents and decision support on top.

> **Private health data.** Shared with the hackathon team only. Don't re-share, upload to third-party
> services, or paste rows into public tools. Originals (CareLink CSVs, Oura API JSON) are *not* in this repo.

| | |
|---|---|
| CGM / pump days | 2026-02-08 → 2026-10-13 (248 days, 244 with ≥ 70 % CGM coverage) |
| Oura days | 2026-02-08 → 2026-10-14 (249 days) |
| Objects | 88,693 + time series (71,174 glucose and 42,038 heart-rate 5-min bins) |
| Quality | 20 / 28 checks passing ([report](data/reports/data_quality.md)) |
| Exported | 2026-10-14 |

## Quickstart

```bash
make setup        # uv sync (install uv: https://docs.astral.sh/uv/)
make validate     # data vs. ontology contract
make quickstart   # example queries: SDK, SQL, DuckDB, polars
```

```python
from t1d_ontology.client import OntologyClient
ont = OntologyClient()
ont.objects("Meal").where("meal_slot = 'lunch'").search_around("meal_bolus").to_polars()
ont.get("Day", "2026-08-14")
ont.sql('SELECT * FROM "SleepSession" ORDER BY bedtime_start_utc DESC LIMIT 5')
```

No Python? `data/ontology.duckdb` has one table per object type (open it in DuckDB, DBeaver, a notebook...),
and every type is a Parquet file in `data/clean/`.

## The ontology

Defined in [`ontology/ontology.yaml`](ontology/ontology.yaml): the contract. The pipeline fails the build if the
data drifts from it. Full property-level dictionary: [`data/reports/ontology_catalog.md`](data/reports/ontology_catalog.md).

| Group | Object type | Kind | Rows | Primary key | What it is |
|---|---|---|---|---|---|
| Calendar | `Day` | object | 248 | `date_local` | One local calendar day |
| Glucose | `GlucoseReading` | object | 81,159 | `reading_id` | One CGM value as received by the pump (Abbott Instinct) |
| Glucose | `GlycemicExcursion` | object | 579 | `excursion_id` | A hypo (<70 for >=15 min; level 2 if <54 for >=15 min) or hyper (>250 for >=15 min) episode, with the insulin/carb context of the 4 h before it |
| Glucose | `FingerstickBg` | object | 309 | `bg_id` | A meter BG, paired with the nearest CGM reading (+/- 5 min) for sensor-accuracy analysis |
| Glucose | `Glucose5Min` | time series | 71,174 | `bin_start_utc` | Regular 5-min CGM grid over the whole era, gaps included (has_data = false) |
| Insulin & meals | `Bolus` | object | 1,024 | `bolus_id` | One user-initiated bolus, assembled from its programmed / delivered / canceled fragments |
| Insulin & meals | `BolusWizardCalc` | object | 1,065 | `wizard_id` | One Bolus Wizard calculation, meaning what you entered and what the pump recommended |
| Insulin & meals | `Meal` | object | 935 | `meal_id` | A carb entry (wizard with carbs > 0) and its glucose response over the next 4 h |
| Devices & pump | `CgmSensor` | object | 20 | `sensor_id` | One physical Instinct sensor, from pairing until the next sensor is paired |
| Devices & pump | `InfusionSet` | object | 98 | `set_id` | One reservoir + infusion-set change (rewind, tubing fill, cannula fill) and its wear period |
| Devices & pump | `PumpAlert` | object | 2,118 | `alert_id` | One pump alert or alarm, with when you cleared it |
| Devices & pump | `PumpSuspension` | object | 426 | `suspension_id` | A period with insulin delivery stopped (by you, by an alarm, or by SmartGuard for a predicted low) |
| Devices & pump | `ClockChange` | object | 23 | `clock_change_id` | A manual change of the pump clock (DST, travel, correction) |
| Sleep & recovery | `OuraDay` | object | 249 | `date_local` | Oura daily summary for a day (from the start of the CGM era, including days after the latest pump export): sleep / readiness / activity / stress scores, temperature deviation, HRV, and the main night with its overnight glucose |
| Sleep & recovery | `SleepSession` | object | 334 | `sleep_id` | One Oura sleep period (main night or nap) with sleep metrics and the glucose / insulin picture while in bed |
| Sleep & recovery | `Workout` | object | 106 | `workout_id` | One Oura-detected or logged workout, with glucose before, during and 12 h after (delayed-low analysis) |
| Sleep & recovery | `HeartRate5Min` | time series | 42,038 | `bin_start_utc` | Oura heart rate in 5-minute bins aligned to the glucose grid (Glucose5Min.bin_start_utc) |

`Day` (`date_local`) is the hub: most types link to it. Intraday questions join on time: `Glucose5Min` and
`HeartRate5Min` share `bin_start_utc`; events carry `ts_utc` / `start_utc`.

### Link types

| Link | Join | |
|---|---|---|
| `day_readings` | GlucoseReading.date_local → Day | |
| `day_boluses` | Bolus.date_local → Day | |
| `day_meals` | Meal.date_local → Day | |
| `day_excursions` | GlycemicExcursion.date_local → Day | |
| `day_alerts` | PumpAlert.date_local → Day | |
| `day_suspensions` | PumpSuspension.date_local → Day | |
| `day_fingersticks` | FingerstickBg.date_local → Day | |
| `day_sensor` | Day.sensor_id → CgmSensor | |
| `day_set` | Day.set_id → InfusionSet | |
| `sensor_readings` | GlucoseReading.sensor_id → CgmSensor | |
| `sensor_meals` | Meal.sensor_id → CgmSensor | |
| `sensor_excursions` | GlycemicExcursion.sensor_id → CgmSensor | |
| `sensor_fingersticks` | FingerstickBg.sensor_id → CgmSensor | |
| `set_meals` | Meal.set_id → InfusionSet | |
| `set_excursions` | GlycemicExcursion.set_id → InfusionSet | |
| `wizard_bolus` | BolusWizardCalc.bolus_id → Bolus | |
| `meal_wizard` | Meal.wizard_id → BolusWizardCalc | |
| `meal_bolus` | Meal.bolus_id → Bolus | |
| `grid_day` | Glucose5Min.date_local → Day | |
| `grid_sensor` | Glucose5Min.sensor_id → CgmSensor | |
| `grid_set` | Glucose5Min.set_id → InfusionSet | |
| `oura_day_day` | OuraDay.date_local → Day | may be unresolved (cross-source) |
| `oura_day_main_sleep` | OuraDay.main_sleep_id → SleepSession | |
| `day_sleeps` | SleepSession.date_local → Day | may be unresolved (cross-source) |
| `day_workouts` | Workout.date_local → Day | may be unresolved (cross-source) |
| `hr_grid` | HeartRate5Min.bin_start_utc → Glucose5Min | may be unresolved (cross-source) |
| `day_notes` | DayNote.date_local → Day | |

### Action types (write-back)

| Action | Effect | Description |
|---|---|---|
| `create_experiment` | create `Experiment` | Commit to trying a change for a period; the platform tracks the metric against your baseline. |
| `update_experiment` | modify `Experiment` | Change an experiment's status or add notes. |
| `add_day_note` | create `DayNote` | Record context for a day (illness, stress, travel, routine change). |

Actions validate typed parameters and write to `data/writeback/` (git-ignored here; created empty on first use).

## Things to know before you model

- **Time.** `*_utc` columns are true UTC, reconstructed from the pump's hand-set clock (DST, travel, typos).
  `*_local` / `date_local` are local wall-clock time where the person actually was (home: America/New_York,
  travels often; `Day.is_travel_day`). Never order a continuous series by local time: it repeats across time zones.
- **Valid days.** Use `Day.is_valid_cgm_day` (≥ 70 % CGM coverage, not partial) for daily glucose metrics.
- **Oura dating.** Oura assigns a night to the morning you wake up, so `OuraDay(d)` describes the night before `Day(d)`.
  Oura days can run past the latest pump export; their links to `Day` are then unresolved (by design).
- **Insulin.** `tdd_u = bolus_u + auto_insulin_u` (SmartGuard). The CareLink CSV under-counts auto-corrections
  (≈ 5–7 U/day vs. the CareLink PDF). `InfusionSet` = reservoir fills, not necessarily tubing/site changes.
- **Pump replaced ~2026-09-26.** Sep 25 is incomplete (gap between exports); Sep 26–27 lack daily auto-insulin totals.
- **Meals** are Bolus Wizard carb entries only; food eaten without a wizard entry is invisible.
- Glucose ranges: very low < 54 ≤ low < 70 ≤ in range ≤ 180 < high ≤ 250 < very high (mg/dL).

More: [`docs/architecture.md`](docs/architecture.md), [`docs/data-sources/`](docs/data-sources/) (how each source
is parsed and corrected), [`docs/decisions/`](docs/decisions/).

## Layout

```
ontology/   ontology.yaml + t1d_ontology (model, validation, actions, client SDK)
pipelines/  t1d_pipelines: how the clean layer is built from CareLink + Oura (needs the private originals to run)
core/       shared settings
config/     pipeline.yaml (thresholds, time zone, source settings)
data/clean/ the clean layer, one Parquet file per object type
data/ontology.duckdb   the same as DuckDB tables
data/reports/          ontology catalog + data-quality report
examples/   quickstart.py
```

## Refreshing

This repo is exported from the private pipeline repo (`scripts/export_data_repo.py` there) after each new
CareLink export / Oura pull. Pull to get fresh data; don't edit `data/` by hand.
