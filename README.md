# Kaizen

**Discovery brief: how can we embed intelligence into the daily workflow of living with type 1 diabetes?**

This hackathon starts with a real workflow and an existing data foundation: insulin pump and continuous glucose monitor (CGM) exports, Oura sleep and recovery data, and an ontology that connects them. The task is to discover where intelligence would make that workflow more useful, then build a small prototype that demonstrates the value.

Start with the person, the question they need answered, and the evidence available. Choose the interface and model after we understand the moment we want to improve.

> **Sensitive health data.** This repository contains one person's health records. Original exports are not included. Do not re-share records or send them to third-party services or hosted models without the data owner's explicit approval. Removing direct identifiers does not establish anonymity.

## Why: reduce the work of making sense of the day

Managing type 1 diabetes involves recurring decisions around meals, exercise, sleep, and changes in routine. The pump, CGM, and ring each capture part of the story. Understanding a difficult night or an unusual day means bringing those pieces together across apps and time windows.

Our working hypothesis is that connected data can reduce the effort of reconstructing what happened, surface patterns worth investigating, and help the person bring better questions to their care team. More charts or a conversational interface only help if they improve a specific part of that work.

Discovery should establish which moments are hardest today, how the person handles them, and what evidence would make an explanation useful enough to trust. The repository gives us observations; it does not yet establish which product experience the person will use.

## How: understand the workflow before designing the intelligence

These are starting hypotheses for interviews and walkthroughs, not a validated account of the person's current routine.

| Moment | Question to explore | Possible role for intelligence | What discovery needs to establish |
|---|---|---|---|
| Reviewing a night or day | What changed, and what else was happening? | Reconstruct a timeline across glucose, meals, sleep, and device events; compare similar periods | Which comparisons help, and which explanations require context we do not record? |
| Reviewing meals or exercise | Is this a recurring pattern or an isolated event? | Retrieve comparable meals or workouts and show outcomes, sample sizes, and exceptions | Whether the comparison is fair and what the person would do with it |
| Preparing for a care visit | What deserves discussion with my clinician? | Draft a concise summary with traceable charts and questions | What the person and clinician currently spend time assembling |
| Following up on an observation | Did the pattern persist, and what did we learn? | Track a user-approved question or experiment against a defined baseline | What context to record and when evidence is sufficient |

An intelligence-assisted workflow could follow this loop:

```text
User question or review moment
  → assemble relevant objects and the time window
  → calculate a comparison and check coverage
  → explain the observation with supporting evidence and uncertainty
  → ask for missing context or propose a next step for review
  → record an approved note or experiment
  → revisit what was learned
```

Some steps need deterministic queries and charts. Others may benefit from retrieval, statistical analysis, or an agent that coordinates tools and explains results. Discovery should identify where each earns its place. Therapy changes belong in discussion with the care team; the prototype should not generate insulin doses or control the pump.

## Current data: what we can investigate

The exported snapshot is dated **2026-10-14**. It covers one person using a Medtronic MiniMed 780G pump with SmartGuard, an Abbott Instinct CGM, and an Oura ring. This is historical exported data; live ingestion and notifications have not been established here.

| Data available | Coverage in the current snapshot | Questions it can support |
|---|---|---|
| Daily pump/CGM summaries | 248 days, 2026-02-08 through 2026-10-13; 244 valid CGM days | How do glucose metrics vary across days and routines? |
| Glucose readings and aligned series | 81,159 readings; 71,174 five-minute bins, including gaps | What happened around a meal, workout, sleep period, or device event? |
| Meals and user boluses | 935 recorded meals; 1,024 boluses; 1,065 Bolus Wizard calculations | How do recorded meal responses differ with timing and starting conditions? |
| Sleep and recovery | 249 Oura days through 2026-10-14; 334 sleep sessions | How do sleep and recovery measures relate to glucose patterns? |
| Workouts and heart rate | 106 workouts; 42,038 five-minute heart-rate bins | How do glucose patterns differ around recorded activity? |
| Excursions and device context | 579 glycemic excursions; 2,118 alerts; 426 suspensions; 20 sensors; 98 reservoir/fill-derived infusion-set records; 23 clock changes | Could device events or changes in timing contextualize an unusual period? |
| User-entered context | `DayNote` and `Experiment` objects available through write actions | What additional context could help interpret an observation and follow up? |

Counts come from [the generated data snapshot](docs/DATA.md). The [quality report](data/reports/data_quality.md) records 28 checks: 20 passing, 3 warnings, 5 notes, and no failing errors. This describes pipeline quality, not clinical validation. Check the [property catalog](data/reports/ontology_catalog.md) before proposing a feature.

### What the data cannot tell us on its own

- **It is one person's observational history.** Associations suggest questions; they do not establish causes or generalize to other people. Report windows, inclusion rules, missingness, and sample sizes.
- **Meal records are Bolus Wizard carb entries.** Unlogged food and treatment of lows may be invisible. Food composition and intent are incomplete.
- **Automated insulin is a daily aggregate.** The export cannot tell us exactly how much SmartGuard added after a particular meal. Source documentation reports under-counting of auto-corrections in the CSV relative to the CareLink PDF.
- **Context is incomplete.** Illness, stress, and changes in routine may require a question to the user. The quality report records Oura readiness on 85% of CGM days.
- **Time and coverage affect comparisons.** Use true UTC for continuous sequences and `Day.is_valid_cgm_day` for daily glucose comparisons. Oura assigns a night to the morning it ends; its latest records can extend beyond the pump export.
- **Device changes affect baselines.** The pump replacement around September 26 leaves incomplete or missing totals on surrounding days. `InfusionSet` marks reservoir/fill events and does not reliably identify every physical site change.

See [source documentation](docs/data-sources/) and [pump-clock reconstruction](docs/decisions/0004-pump-clock-reconstruction.md).

## Where intelligence could fit: hypotheses to test

The existing [workflow board](apps/ontology-manager/workflows.yaml) contains seed ideas and reported associations around bedtime glucose, meal timing, sleep, recovery, and exercise. Treat these as discovery inputs. Reproduce a comparison with explicit definitions and sample sizes before using it to justify a feature. The existing summary numbers do not validate a proposed intervention.

| Opportunity | Evidence to assemble | Prototype output | How we would assess value |
|---|---|---|---|
| Explain an unusual night | `SleepSession`, `Glucose5Min`, `Meal`, `Bolus`, and device context via `Day` | A timeline, comparable nights, and plausible explanations separated from observations | Can the person understand the night faster, verify the evidence, and correct missing context? |
| Review meal or workout patterns | `Meal`, `BolusWizardCalc`, `Workout`, and glucose windows | Comparable events with counts, outcomes, and exceptions | Are comparisons relevant enough to support a useful question for the care team? |
| Prepare a care-visit brief | `Day`, excursions, meals, and device history | A reviewable summary with charts and a short list of questions | Does it reduce preparation effort while preserving the person's priorities? |
| Close the learning loop | A defined baseline plus `Experiment` and `DayNote` | A follow-up comparison that can also say “insufficient evidence” | Does the person return to the question and learn something they could not easily track before? |

**Suggested first slice:** a retrospective review of one unusual night. It uses connected data already available and lets us test whether an explanation is useful before investing in live triggers or predictions. Select the first workflow based on user walkthroughs and evidence we can reproduce.

## What discovery should produce

1. **A walkthrough of the current workflow.** Reconstruct a recent difficult day or night using the person's usual tools. Capture steps, decisions, missing context, and effort.
2. **One defined opportunity.** Name the user, moment, question, current workaround, and desired outcome. Separate interview findings from assumptions.
3. **An evidence-backed example.** Identify the objects and joins, reproduce the analysis, show coverage and sample sizes, and document unknowns.
4. **A small prototype at that moment.** Show the evidence, explanation, and user review together, using the existing ontology and tools where they help.
5. **A decision about what comes next.** Define success criteria before evaluation. Assess usefulness and factual accuracy against the current workflow, then retain, revise, or drop the idea.

For each proposal, capture:

```text
Why: user need, moment, current workaround, desired outcome
Evidence: objects, fields, time window, comparison, coverage, sample sizes
How: trigger, deterministic analysis, intelligence role, interface, user review
Unknowns: missing context, alternative explanations, failure cases
Validation: user walkthrough, baseline experience, success criteria
```

## What already exists

The data and exploration foundation are present. The workflow definitions are an ideation board: some are labeled `prototype`, but that label alone does not establish a running or validated workflow.

The repository includes clean Parquet data, a portable DuckDB database, an ontology, an exploration app, and schema-generated agent tools. The agent endpoint requires `confirm: true` for write tools; an integrating app must obtain user agreement before sending that flag. It is not an independent approval system. Scheduling, live notifications, predictive performance, and clinical effectiveness remain work to investigate and validate.

The technical guides below explain how to explore the foundation and build a prototype.

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

The agent tool interface is available: `GET /api/agent/tools?format=anthropic` returns tool definitions generated
from the ontology, `POST /api/agent/call` executes them, and `GET /api/agent/context` is a system-prompt primer
with the domain conventions. An agent can answer "why were my nights worse last week?" by chaining
`aggregate` → `search_around` → `run_sql`, then propose `create_experiment`. The integrating app must ask the user before confirming a write.
See [apps/ontology-manager/README.md](apps/ontology-manager/README.md).

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
