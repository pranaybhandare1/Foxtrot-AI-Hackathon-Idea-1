# Source notes: Oura ring (API v2)

Status: **integrated**: landing → raw → transformed → clean, four ontology types, quality checks O1–O5,
timeline overlays and the Sleep & recovery page.

## Layers

| Layer | Output |
|---|---|
| raw | `oura_documents` (every document as JSON text, lineage by pull) · `oura_heartrate` |
| transformed | `oura_daily`, `oura_sleep`, `oura_workout`, `oura_heartrate` (UTC, deduped: latest pull wins), `oura_tz_observations` |
| clean | `OuraDay`, `SleepSession`, `Workout` (with glucose / insulin context) · `HeartRate5Min` (on the glucose grid) |

Scope: every Oura day from the start of the CGM era, including days after the latest CareLink export, so
sleep and recovery stay current when pump data lags. The links to `Day` / `Glucose5Min` are declared
`required: false` (unresolved until the next pump export; glucose features are null there). All Oura types
are `optional: true`, so the build stays valid without an Oura account.

## Time-zone correction (the cross-source win)

Oura timestamps carry the phone's real UTC offset. `oura_tz_observations` (sleep / workout start and end)
feeds `ObservedTimeZones` in the CareLink clock model: where the pump-derived local offset and Oura disagree,
the more recent evidence wins (a >= 30 min pump clock change after the observation = you reset the pump on
arrival). First pull: 181/189 nights agreed before correction, 189/189 after. The 8 fixed nights were a pump
left on Central time at home (Feb 8-11) and trips with no pump clock change (Jul 9-10 West Coast,
Jul 15-16 Central). UTC was never affected, only local-time labels.

## Profile of the first pull (2026-01-01 → 2026-10-14)

382 sleeps (253 main nights, 119 short sleeps, 10 late naps) · ~250 days of daily scores ·
108 workouts (flexibility, walking, cycling, core, …) · 354k HR samples (mostly 5-s workout samples,
5-min awake/rest) · tags nearly unused (1).

## Access

- Personal access tokens were deprecated by Oura in December 2025; the only access is **OAuth2
  authorization-code flow** via an API application (https://cloud.ouraring.com/oauth/applications).
- App settings: redirect URI **`http://localhost:8766/callback`** (the one-shot local server in
  `sources/oura/auth.py` catches it, validating `state`); scopes as listed in `config/pipeline.yaml`.
- Credentials live in `.env` (gitignored; template `.env.example`). Tokens live in
  `data/secrets/oura_token.json` (gitignored, chmod 600). Oura rotates refresh tokens; every refresh
  is persisted.

```bash
make oura-connect     # once: opens the consent page in your browser
make oura-pull        # backfill from 2026-01-01, then incremental (re-fetches the last 3 days)
make oura-status
```

## Landing contract

`data/landing/oura/pull_<UTC timestamp>/<endpoint>.json` with `{endpoint, params, documents}` plus a
`_manifest.json` (window, request count, per-endpoint counts, endpoints skipped for missing scope).
Batches are read-only; overlapping documents are deduplicated by `id` downstream (latest pull wins).

## What the API offers (v1.41 spec)

Daily: `daily_sleep`, `daily_readiness` (incl. temperature deviation and contributors),
`daily_activity`, `daily_stress`, `daily_resilience`, `daily_spo2`, `daily_cardiovascular_age`,
`vO2_max`. Sessions: `sleep` (HRV, HR, stages, bedtime start/end), `sleep_time`, `workout`, `session`,
`rest_mode_period`. Time series: `heartrate`. User input: `tag`, `enhanced_tag`.
All timestamps carry their real UTC offset, which lets us detect travel days that the pump clock missed.

## Rate limits

Per-token and per-application limits; `429` responses carry `Retry-After`, which the client honours.
Oura recommends webhooks, but those need a public URL, which this local-only app deliberately doesn't expose.
