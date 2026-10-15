# pipelines/ (t1d-pipelines)

Source ingestion and data quality. Provides the `t1d` CLI:

```bash
uv run t1d run                          # all steps
uv run t1d run --from transformed       # resume from a step
uv run t1d run --from quality --to quality
```

Steps: `landing → raw → transformed → clean → ontology → quality`.

```
src/t1d_pipelines/
├── cli.py                     step orchestration
├── sources/carelink/
│   ├── landing.py             checksum-verified immutable copy of an export batch
│   ├── raw.py                 3-section CSV parser → raw Parquet (lineage, no PII)
│   ├── clock.py               pure functions: pump clock → UTC / local time (heavily tested)
│   ├── transformed.py         typing, event classification, time reconstruction, dedupe
│   └── clean/                 one module per object family
│       ├── devices.py         CgmSensor, InfusionSet, PumpSuspension, ClockChange
│       ├── glucose.py         GlucoseReading, Glucose5Min, GlycemicExcursion, FingerstickBg
│       ├── insulin.py         Bolus, BolusWizardCalc, Meal (+ response features)
│       ├── alerts.py          PumpAlert
│       └── day.py             Day (the hub)
└── quality/checks.py          22 checks; failing errors stop the build
```

Read [docs/data-sources/carelink.md](../docs/data-sources/carelink.md) before changing CareLink logic.
