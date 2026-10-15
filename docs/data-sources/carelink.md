# Source notes: Medtronic CareLink "Data Export (CSV)"

Device: MiniMed 780G (MMT-1884) with SmartGuard. CGM: Guardian 4 until 2026-01-20,
then **Abbott Instinct from 2026-02-08** (firmware 27.11.6). Everything below was found by profiling
the 2026-09-26 export (11 files, 102,945 rows). Re-check it when a new export or firmware arrives.

## File layout

- UTF-8 with BOM, CRLF line endings. Files are ~30-day windows named `carelink_<start>_to_<end>.csv`.
- Lines 1–3 hold metadata (patient name/DOB, device, firmware, serial, CGM). PII is dropped at raw.
- **Three sections per file**, each with its own `-------` marker line and repeated header:

| Section | Marker label | Contents |
|---|---|---|
| pump | `-------` | Discrete pump events |
| pump_aggregated_auto_insulin | `Aggregated Auto Insulin Data` | **One row per day of SmartGuard auto insulin** (selected / delivered) |
| sensor | `-------` (Sensor) | CGM readings, sensor exceptions, day markers |

- 54 columns in every section. Values may contain quoted commas, so use a real CSV parser.
- Rows are **newest first**. `Index` runs continuously across sections within a file and restarts per file.

## Row types (pump section)

A row is one event; the populated columns determine its type (see `PUMP_RULES` in `transformed.py`).
Notable ones:

- **Boluses come in fragments** that share a `Bolus Number`: *programmed* (selected U), *delivered*
  (selected + delivered U, stamped at completion), *canceled*. Numbers are reused, and most cancel records
  (353 of 357) don't belong to any live bolus. A cancel counts only if it lands inside a bolus's delivery window.
- **Bolus Wizard** rows (`BWZ Status`) sit at the same second as the programmed fragment. A "detail" row
  at the same timestamp carries unabsorbed insulin and the final estimate.
- `Bolus Source`: `CLOSED_LOOP_BG_CORRECTION_AND_FOOD_BOLUS` (meal bolus in SmartGuard),
  `CLOSED_LOOP_BG_CORRECTION` (user correction in SmartGuard), `BOLUS_WIZARD` (manual mode).
- **SmartGuard auto basal and auto-corrections are not individual events.** They exist only in the daily
  aggregate section, which is the main analytical limitation of this source.
- `Basal Rate` rows are the *manual* schedule (1.3 U/h 00–07, 1.35 U/h 07–24). They aren't delivered while SmartGuard is active.
- `Suspend`: `USER_SUSPEND`, `NEW_RESERVOIR_AND_SET`, `ALARM_SUSPEND`, `PLGM_PREDICTED_LOW_SG`,
  `LOWSG_SUSPEND`, and `NORMAL_PUMPING` (resume). About 1.3 user suspends a day, with a median of 73 min each.
- Site change = `Rewind` → `Tubing Fill` → `Cannula Fill` (cannula volume is usually 0).
- BLE pairing events name each **Instinct sensor by serial** ("Unknown device (0RFD2H0JW) was added").
  A serial is re-added on every re-pairing, so sensor identity = serial.
- About 400 pump rows carry only a timestamp. They are kept in transformed and dropped from clean.

## Sensor section

- Instinct readings have **no ISIG**; Guardian 4 readings do. This is a clean way to detect the switch.
- The pump records a reading every 5 min, and about 10% of samples are re-received 1–3 min later with the same
  value. The 5-minute grid (`Glucose5Min`) collapses them.
- Readings are stamped **when the pump receives them**, using the pump clock at that moment. Backfilled
  readings get `receipt_clock - age`.
- Exceptions: `SENSOR_INIT_CODE` (warm-up, about 1 h), `SENSOR_ERROR`, `SENSOR_FAILED_BG_CHECK`, `SENSOR_END_OF_LIFE`.
- "Start/End of the day" markers carry no information.

## Clocks and time zones

The pump clock is set by hand, and there are 31 `New Device Time` changes in this export, including:

| When | Change | Meaning |
|---|---|---|
| 2026-02-11 | +1 h | Pump moved from UTC−6 to UTC−5 |
| 2026-03-08 20:52 | +1 h | US DST applied about 19 h late |
| 2026-06-30 / 07-03 | −29 min / +29 min | Accidental clock slip |
| 2026-07-11 / 07-13 | −3 h / +3 h | West-coast trip (UTC−7) |
| 2026-08-10 | +6 h | Europe trip (UTC+2) |
| 2026-08-18 | +18 h, then −24 h 24 s later | Wrong date typed, then fixed (net −6 h, back home) |
| 2026-09-20 | −4, −16, +19, −1 min | Fiddling |

Reconstruction (`clock.py`): UTC = device time + the sum of later clock deltas − the final offset
(configured, UTC−4 at export). Pump rows are placed by their true sequence. Sensor rows are placed by receipt
order, advancing a segment when the clock passes a change's old value or drops on a backward change.
After the Aug 18 typo, 10 `SENSOR_ERROR` rows kept a +24 h sensor clock; these are repaired and flagged `ts_repaired`.
Check **T5** confirms alignment: in every clock segment, pump alert values best match CGM readings at a
0–5 min shift, versus 30–130 mg/dL error at ±1 h.

**Limitation:** if you travel without changing the pump clock, local time stays on home time for those days.
Oura's timezone data will be able to correct this later.

## Reconciliation with CareLink's own PDF report

We compared the pipeline against CareLink's 14-day PDF ("Assessment and Progress", 2026-09-12 → 09-25,
generated 2026-09-26):

| Metric | CareLink PDF | Pipeline |
|---|---|---|
| Average SG ± SD | 172 ± 56 | 170 ± 56 |
| GMI / CV | 7.4% / 32.8% | 7.4% / 33.2% |
| >250 / 140–250 / 70–140 / <70 | 10 / 54 / 35 / 1% | 9.7 / 53.2 / 36.4 / 0.8% |
| Average meter BG | 178 ± 83 | 178 ± 83 (exact) |
| User bolus insulin / day | 24.4 U | 24.7 U |
| Meal summary, lunch (n, carbs) | 19, 28 ± 11 g | 19, 28 ± 11 g |
| Day with no auto-corrections (09-12): TDD / auto | 46.8 / 21.7 U | 46.8 / 21.7 U (exact) |
| **SmartGuard auto insulin / day** | **40.1 U** (23.1 basal + 17.0 auto-correction) | **33.1 U** |
| Reservoir change interval | 1.5 days | 1.4 days (our `InfusionSet`) |
| **Set change interval** | **3.3 days** | not yet distinguished |

Two findings:

1. **Auto-correction under-count.** The CSV's daily "Aggregated Auto Insulin" matches CareLink exactly on
   days without auto-corrections, but on other days it carries only ~75% of the auto-correction insulin
   CareLink reports, so TDD is ~5–7 U/day (≈9%) lower than CareLink's. Per-event auto-corrections do
   appear in the PDF's Logbook, but not in the CSV.
2. **Reservoir vs. set changes.** `InfusionSet` is actually every *reservoir/tubing fill* (rewind → fills).
   CareLink's "Set Change" markers coincide with fills whose tubing prime is ≥ ~8 U (7/7 agreement over this
   window). Until that rule is validated over more data, "set day" analyses really mean "reservoir day".

## Known limitations

- Per-meal loop response can't be measured, because auto insulin exists only as a daily total.
- Meals are Bolus Wizard carb entries. Food without a wizard entry (for example, treating a low) is invisible.
- Carb counts are the user's estimates.
