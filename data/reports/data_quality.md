# Data quality report: CareLink (Instinct era)

_Generated 2026-10-14 by `t1d run`._

- Instinct era: **2026-02-08 → 2026-10-13** (248 days, 244 valid CGM days)
- Result: **20/28 checks passed**, 0 failing errors, 3 warnings

| ID | Layer | Severity | Status | Check | Detail |
|---|---|---|---|---|---|
| L1 | landing | error | **PASS** | Landed files are byte-identical to what was recorded at landing | 23 files in 2 batch(es); changed since landing: none |
| L3 | landing | warn | **WARN** | Every landed file is listed in the export's checksums.sha256 | not in checksums.sha256 (hash recorded at landing instead): ['carelink_2026-09-26_to_2026-10-13.csv']. Add them to ~/CareLink-raw/checksums.sha256 to verify against the source. |
| L2 | landing | error | **PASS** | Export windows are contiguous (no gaps, no overlaps) | windows chain day-to-day |
| R1 | raw | error | **PASS** | Every file has the pump, aggregated-insulin and sensor sections | 23 files, 212,690 rows; missing sections in: none |
| R2 | raw | warn | **PASS** | All files come from the same pump serial | serials: ['NG*******H'] |
| T1 | transformed | info | **NOTE** | Rows that carry no payload (dropped from clean) | 1,063 payload-less rows (pump rows with only a timestamp, sensor start/end-of-day markers) |
| T2 | transformed | error | **PASS** | Pump events: reconstructed UTC is monotonic in pump sequence | 0 backward steps > 60 s across 13,564 pump events |
| T3 | transformed | error | **PASS** | Sensor rows: reconstructed UTC is monotonic in receipt sequence | 0 backward steps > 2 min across 94,059 sensor rows |
| T4 | transformed | info | **NOTE** | Timestamps repaired (whole-day sensor clock errors) | 10 rows repaired: [('sensor_exception', 10)] |
| T5 | transformed | error | **PASS** | Pump and sensor clocks agree in every clock segment (alert values vs CGM) | UTC-7h n=10 best shift +5 min (err 6 vs ±60 min 34); UTC-5h n=112 best shift +5 min (err 8 vs ±60 min 44); UTC-4h n=722 best shift +5 min (err 7 vs ±60 min 52); UTC+2h n=31 best shift +5 min (err 6 vs ±60 min 58) |
| T6 | transformed | error | **PASS** | Instinct era has no ISIG values (Abbott sensors don't report ISIG) | 0 ISIG values after era start; first Instinct reading 2026-02-09 01:50:40 UTC |
| T7 | transformed | info | **NOTE** | Cross-row duplicates removed | raw 212,690 rows -> transformed 108,555 (104,135 exact duplicates collapsed) |
| C1 | clean | error | **PASS** | CGM values are within the sensor's reportable range (40-400) | 0 out-of-range of 81,159; 2 at 400 (= '>=400') |
| C2 | clean | error | **PASS** | 5-min grid: at most 3 readings per bin, every bin has a UTC offset | 71,174 bins, 96.3% with data, max 3 readings/bin |
| C3 | clean | warn | **PASS** | Sensors: wear <= 15.5 days and coverage >= 90% | 20 sensors, median wear 14.3 d, median coverage 97.6%; ended early (<14 d): [('0R8G3HXHT', 8.672), ('0Q2DHPMTV', 10.172), ('0RFD2L014', 13.514), ('0RFD2H0JW', 13.951), ('0RDJKDAUF', 2.882), ('0TF90PG0R', 0.14)]; flagged: none |
| C4 | clean | error | **PASS** | Boluses: delivered <= programmed, non-negative delivery time | 1024 boluses; over-delivered 0; negative duration 0; partial 2 |
| C5 | clean | error | **PASS** | Every delivered wizard calculation links to a bolus | 100.0% of 1024 delivered wizard calcs linked |
| C6 | clean | error | **PASS** | Day totals reconcile with their objects (insulin, carbs, hypos) | differences: {'bolus_u': 0.0, 'carbs_g': 0.0, 'n_hypo': 0} |
| C7 | clean | error | **PASS** | Excursions of the same kind never overlap | 0 overlaps among 579 excursions |
| C8 | clean | warn | **WARN** | Days with CGM coverage below 70% | 2 of 248 days: [('2026-07-29', 0.5764), ('2026-09-25', 0.3438)] |
| C9 | clean | warn | **WARN** | Total daily dose within a plausible band (10-150 U) on full days | median TDD 57.9 U; outside band: [('2026-09-26', None), ('2026-09-27', None)] |
| C10 | clean | info | **NOTE** | Infusion sets replaced within 12 h (possible site failures) | 98 sets, median wear 64 h; <12 h: [('set_20260423T1207', 8.38), ('set_20260729T1328', 6.14), ('set_20260920T1732', 1.41), ('set_20260920T1856', 1.43)] |
| C11 | clean | info | **PASS** | Sensor vs fingerstick agreement (MARD) | 298 paired fingersticks: MARD 12.9%, median bias -9 mg/dL (sensor minus meter) |
| O1 | clean | warn | **PASS** | Oura covers most CGM days (readiness present) | 85% of 248 CGM days have an Oura readiness score |
| O2 | transformed | warn | **PASS** | Local time agrees with Oura's observed time zone on every night | 207/207 nights agree; disagreeing: [] |
| O3 | transformed | info | **NOTE** | Pump-clock local times corrected using Oura | 3,455 events on 15 days re-timed to Oura's observed time zone (wrong pump clock or trips without a pump clock change) |
| O4 | clean | error | **PASS** | Sleep sessions are well-formed (end after start, sleep <= time in bed) | 0 malformed of 334 sessions |
| O5 | clean | error | **PASS** | Heart rate is physiological (25-230 bpm) | 0 out-of-range of 42,038 5-min bins |

## Clean-layer row counts

| Table | Rows |
|---|---|
| glucose_reading | 81,159 |
| glucose_5min | 71,174 |
| cgm_sensor | 20 |
| infusion_set | 98 |
| bolus | 1,024 |
| bolus_wizard_calc | 1,065 |
| meal | 935 |
| glycemic_excursion | 579 |
| pump_alert | 2,118 |
| pump_suspension | 426 |
| fingerstick_bg | 309 |
| clock_change | 23 |
| day | 248 |

## Known limitations of this source

- SmartGuard auto basal and auto-correction boluses exist only as a **daily total** (`Day.auto_insulin_u`). Per-meal questions like "how much did the loop add after dinner" can't be answered from this export. User boluses are exact.
- The CSV's daily auto-insulin total under-counts auto-corrections vs. CareLink's PDF (~5-7 U/day, ~9% of TDD on recent days); see docs/data-sources/carelink.md.
- `InfusionSet` marks reservoir/tubing fills; true infusion-set changes (~every 3.3 days) are not yet distinguished.
- Meals are wizard carb entries. Food eaten without a wizard entry (e.g. treating a low) is invisible.
- Local time assumes the final pump clock was UTC-4 (EDT) at export and home = America/New_York (New Jersey) (config). Every earlier clock segment is derived from the logged clock changes, and T5 validates it independently.
- Local time follows the pump clock, corrected by Oura's observed phone time zone where they disagree (O2/O3); days without Oura data rely on the pump clock alone.
- The manual basal schedule (1.3 / 1.35 U/h) is kept in transformed but is not delivered while SmartGuard is active.
- Backward clock changes smaller than the CGM receipt interval can mis-time a few readings by at most |change| (<= 1 min in this data).
