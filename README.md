# Pranay360

**A personal health ontology for type 1 diabetes**: insulin pump, CGM and Oura ring data, unified into one
validated data layer and modelled as an ontology (objects, links and actions, Palantir Foundry style). It's the
foundation for building decision support, workflows and AI agents that help manage glucose, sleep and recovery.

This repo is the hackathon starting point: the data, the ontology, the pipeline code that produced it, and an
**Ontology Manager** app for exploring the data and ideating on top of it.

> **Private health data.** Shared with the team for the hackathon only. Don't re-share, upload rows to
> third-party services, or paste them into public tools. The original exports are not in this repo, and the
> data carries no name or device serials.

---

## The person and the problem

One person living with **type 1 diabetes**:

- **Medtronic MiniMed 780G** insulin pump running **SmartGuard** (a closed loop that adjusts insulin every 5 min)
- **Abbott Instinct** continuous glucose monitor (CGM), a reading every 5 minutes, since 2026-02-08
- **Oura ring**: sleep, HRV, readiness, temperature, activity, workouts and heart rate
- Home time zone New Jersey (America/New_York), travels often

Managing T1D is a stream of daily decisions (how much insulin, when to eat, what to do before exercise or bed)
made with data split across apps that don't talk to each other. Pranay360 brings it into one place and asks
three questions, the **three pillars**:

| Pillar | Question |
|---|---|
| **Glucose** | What is my glucose doing, and why? (meals, insulin, time of day, devices) |
| **Sleep & recovery** | How are sleep, HRV, readiness and activity trending? |
| **Connections** | How do they affect each other, and what should I change? |

### What the data already says

Associations across the whole history (one person; descriptive, not causal):

| Finding | Exposed | Baseline |
|---|---|---|
| Going to bed above 180 mg/dL → overnight time in range | 69 % | 85 % |
| Bolusing after glucose already started rising → post-meal rise | +75 mg/dL | +56 mg/dL |
| Food within 3 h of bed → overnight time in range | 73 % | 81 % |
| Sleeping < 6.5 h → next-day time in range | 62 % | 67 % |
| Readiness < 70 → time in range | 60 % | 66 % |
| ≥ 10k steps → total daily insulin | 53 U | 59 U |
| Cycling → low within 12 h | 4 of 6 rides | 24 % of other workouts |

Each of these is a candidate workflow or agent behaviour: see [the Ontology Manager](#the-ontology-manager-app).

---

## Architecture

```
 Sources                     Medallion pipeline (private repo)                       This repo
 ───────                     ─────────────────────────────────                       ─────────
 CareLink CSV  ─┐   landing ──▶ raw ──▶ transformed ──▶ clean ──▶ validate ──▶  data/clean/*.parquet
 (pump + CGM)   │   (exact     (strings, (typed, UTC-    (one table  (against    data/ontology.duckdb
                ├─▶  bytes,     lineage,  corrected,      per object  ontology.   ontology/ontology.yaml
 Oura API v2  ─┘   checksums)  no PII)   deduped)        type)       yaml)       apps/ontology-manager
```

- **Medallion layers.** Each layer has a contract: landing is immutable and checksum-verified, raw keeps
  every source row with lineage, transformed is typed and time-corrected, clean holds one table per ontology
  object type with analysis features (glucose response per meal, overnight glucose per sleep, and so on).
- **The hard part is time.** The pump clock is set by hand (DST, travel, typos). True UTC is reconstructed from
  the pump's logged clock changes and cross-checked against the CGM and Oura's observed time zones
  (207/207 nights agree). See [ADR 0004](docs/decisions/0004-pump-clock-reconstruction.md).
- **Quality gates.** 28 checks run on every build, and an error fails it
  ([report](data/reports/data_quality.md)).

Only the clean layer and the ontology are shared here; the originals stay private. Details:
[docs/architecture.md](docs/architecture.md), [docs/data-sources/](docs/data-sources/), [docs/decisions/](docs/decisions/).

---

## The ontology layer

The ontology is the contract between the data and everything built on it: apps, analytics and agents speak in
**objects and links**, not tables. It is declared in one file, [`ontology/ontology.yaml`](ontology/ontology.yaml),
and the build **fails** if the data drifts from it. Full guide: **[docs/ONTOLOGY.md](docs/ONTOLOGY.md)**.

| Concept | What it is here |
|---|---|
| **Object types** (19) | Day, GlucoseReading, Meal, Bolus, BolusWizardCalc, GlycemicExcursion, CgmSensor, InfusionSet, PumpAlert, PumpSuspension, FingerstickBg, ClockChange, OuraDay, SleepSession, Workout, Experiment, DayNote + time series Glucose5Min, HeartRate5Min |
| **Properties** | Typed (string, integer, double, boolean, date, timestamp) with descriptions; primary key + title |
| **Link types** (27) | Declared by a foreign key, e.g. `meal_bolus: Meal.bolus_id → Bolus`, `day_sleeps: SleepSession.date_local → Day` |
| **Action types** (3) | The only way to write: `create_experiment`, `update_experiment`, `add_day_note` (typed, validated parameters) |
| **Groups** | Calendar · Glucose · Insulin & meals · Devices & pump · Sleep & recovery · Lifestyle (write-back) |

```
                    CgmSensor ──── GlucoseReading
                        └───────── GlycemicExcursion
 OuraDay ──────┐
 SleepSession ─┤
 Workout ──────┼──── Day ────┬── Meal ── Bolus ── BolusWizardCalc
 DayNote ──────┘             ├── PumpAlert · PumpSuspension · FingerstickBg · GlucoseReading
                             └── CgmSensor · InfusionSet   (the sensor / set worn that day)
 Glucose5Min ── HeartRate5Min       5-min grid, joined on bin_start_utc     ClockChange: standalone
```

`Day` (`date_local`) is the hub every source hangs off. Current coverage and row counts:
**[docs/DATA.md](docs/DATA.md)** (regenerated on every refresh).

### Using it

```python
from t1d_ontology.client import OntologyClient

ont = OntologyClient()
lunches = ont.objects("Meal").where("meal_slot = 'lunch' AND rise_to_peak_mgdl > 100")
lunches.count()
lunches.search_around("meal_bolus").to_polars()          # Meal → Bolus
ont.get("Day", "2026-08-14")                              # one object
ont.sql('SELECT * FROM "SleepSession" ORDER BY bedtime_start_utc DESC LIMIT 5')
```

Or skip Python: `data/ontology.duckdb` has one table per object type, and `data/clean/` has one Parquet file each.

---

## The Ontology Manager app

A Foundry Ontology Manager look-alike for **understanding the data** and **ideating what to build** on it.
Source: [`apps/ontology-manager/`](apps/ontology-manager/).

```bash
make setup     # once: Python packages (needs uv: https://docs.astral.sh/uv/)
make om        # builds the UI and serves http://127.0.0.1:8770
```

| Section | What it does |
|---|---|
| **Discover** | Object types as cards, by group |
| **Object types** | Each type's Overview, **Properties** (with live data profiles: null %, distinct values, ranges, top values), Link types, Datasources (lineage), Actions and **Objects** (search, filter, open an object and follow its links) |
| **Link types · Action types · Graph** | Every relationship; every write action (run it from a generated form); the ontology as an interactive graph |
| **Explore & visualize** | Read-only SQL over the ontology with an instant chart builder, plus starter questions that span the pillars |
| **Workflows** | The ideation board: workflow ideas (trigger, reads, writes, visuals, agent role, evidence) from [`workflows.yaml`](apps/ontology-manager/workflows.yaml), plus which object types are still unused |
| **Agent tools** | The ontology as typed tools for an LLM agent (query, search-around, aggregate, SQL, and actions behind confirmation). Try any call, then copy the tool definitions, the ontology primer and an example Claude agent loop |

### Agentic intelligence: where to start

The agent layer is already wired: `GET /api/agent/tools?format=anthropic` returns tool definitions generated
from the ontology, `POST /api/agent/call` executes them, and `GET /api/agent/context` is a system-prompt primer
with the domain conventions. An agent can answer "why were my nights worse last week?" by chaining
`aggregate` → `search_around` → `run_sql`, then propose `create_experiment`, which the user must confirm.
See [apps/ontology-manager/README.md](apps/ontology-manager/README.md).

---

## Hackathon ideas

Seeded in [`workflows.yaml`](apps/ontology-manager/workflows.yaml) (add yours):

1. **Morning briefing agent**: last night + today's focus, from 14-day trends.
2. **Bedtime check-in**: catch a high or late meal before sleep (the strongest signal in the data).
3. **Pre-bolus & meal coach**: grade each meal response and build the pre-bolus habit.
4. **Exercise low-prevention**: Temp Target reminders before rides; watch the 12-hour delayed-low window.
5. **Insight → experiment → result**: an agent that turns findings into 2-week experiments and reports honestly.
6. **Endo visit prep**: a 14-day report plus questions for the endocrinologist, each backed by a chart.
7. **Models**: predict the next 30–60 min of glucose; next-day TIR from sleep and readiness; meal-response
   regression (carbs, pre-bolus timing, starting glucose, time of day).

---

## Things to know before you model

- **Time.** `*_utc` is true UTC. `*_local` / `date_local` is wall-clock time where the person was. Never sort a
  continuous series by local time: it repeats across time zones.
- **Valid days.** Use `Day.is_valid_cgm_day` (≥ 70 % CGM coverage, not partial) for daily glucose metrics.
- **Oura dating.** `OuraDay(d)` is the night that ended on the morning of `d`. Oura can run ahead of pump data;
  those links to `Day` are unresolved by design.
- **Insulin.** `tdd_u = bolus_u + auto_insulin_u`. The CareLink CSV under-counts SmartGuard auto-corrections
  (~5–7 U/day). `InfusionSet` = reservoir fills (not necessarily site changes).
- **Device events.** The pump was replaced around 2026-09-26: Sep 25 is incomplete and Sep 26–27 lack daily
  auto-insulin totals.
- **Meals** are Bolus Wizard carb entries only.
- **Ranges (mg/dL):** very low < 54 ≤ low < 70 ≤ **in range** ≤ 180 < high ≤ 250 < very high. Targets: TIR > 70 %,
  below 70 < 4 %.
- Not medical advice: findings are for discussion with the care team.

---

## Repo layout

```
apps/ontology-manager/   the Ontology Manager app: api/ (FastAPI), web/ (React), workflows.yaml
ontology/                ontology.yaml + t1d_ontology (model, validation, actions, client SDK)
pipelines/               how the clean layer is built (needs the private originals to run)
core/  config/           shared settings, pipeline config
data/clean/              the clean layer: one Parquet file per object type
data/ontology.duckdb     the same as DuckDB tables
data/reports/            ontology catalog (every property) + data-quality report
docs/                    ONTOLOGY.md · DATA.md (generated) · architecture · data sources · decisions
examples/quickstart.py   SDK, SQL, DuckDB and polars in one script
```

| Command | |
|---|---|
| `make setup` | install (uv) |
| `make validate` | check the data against the ontology contract |
| `make test` | run the tests |
| `make quickstart` | example queries |
| `make om` / `make om-dev` + `make om-api` | run the Ontology Manager / develop it with hot reload |

## Refreshing the data

The data comes from a private pipeline repo. After a new pump export or Oura sync, `make pipeline &&
make export-data` there refreshes only `data/`, `ontology/`, `pipelines/`, `core/`, `config/` and the generated
docs here; it never touches `apps/` or anything else the team adds. Pull to get fresh data, and don't hand-edit
those folders.
