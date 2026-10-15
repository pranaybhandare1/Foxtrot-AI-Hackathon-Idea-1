"""Oura landing: pull raw API documents into an immutable, timestamped batch.

    data/landing/oura/pull_<UTC timestamp>/<endpoint>.json   {"endpoint", "params", "documents": [...]}
    data/landing/oura/pull_<UTC timestamp>/_manifest.json    window, counts, skipped endpoints

The first pull backfills from `backfill_start`; later pulls start `overlap_days` before the previous
pull's end (Oura revises recent days). Overlapping documents are deduplicated downstream by `id`
(latest pull wins), exactly like overlapping CareLink exports.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from t1d_core.settings import Config

from t1d_pipelines.sources.oura.auth import access_token
from t1d_pipelines.sources.oura.client import OuraApiError, OuraClient

SKIPPABLE = {403, 404}  # scope not granted / data type unavailable for this account


def _root(cfg: Config) -> Path:
    return cfg.layers.landing / "oura"


def previous_pulls(cfg: Config) -> list[dict]:
    root = _root(cfg)
    manifests = sorted(root.glob("pull_*/_manifest.json")) if root.exists() else []
    return [json.loads(m.read_text()) for m in manifests]


def pull(cfg: Config, since: date | None = None, client: OuraClient | None = None, today: date | None = None) -> dict:
    oura = cfg.raw["sources"]["oura"]
    today = today or date.today()
    if since is None:
        done = [p for p in previous_pulls(cfg) if p.get("status") == "complete"]
        since = (
            date.fromisoformat(max(p["window"]["end"] for p in done)) - timedelta(days=oura["overlap_days"])
            if done
            else date.fromisoformat(oura["backfill_start"])
        )
    end = today + timedelta(days=1)  # include today's partial data
    client = client or OuraClient(lambda: access_token(cfg))

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")  # microseconds: back-to-back pulls never collide
    dest = _root(cfg) / f"pull_{stamp}"
    dest.mkdir(parents=True, exist_ok=False)
    counts: dict[str, int] = {}
    skipped: dict[str, str] = {}

    def write(endpoint: str, params: dict, docs: list[dict]) -> None:
        (dest / f"{endpoint}.json").write_text(json.dumps({"endpoint": endpoint, "params": params, "documents": docs}))
        counts[endpoint] = len(docs)

    for ep in oura["daily_endpoints"]:
        params = {"start_date": since.isoformat(), "end_date": end.isoformat()}
        try:
            write(ep, params, list(client.paginate(f"/v2/usercollection/{ep}", params)))
        except OuraApiError as e:
            if e.status not in SKIPPABLE:
                raise
            skipped[ep] = str(e)

    chunk = timedelta(days=oura["timeseries_chunk_days"])
    for ep in oura["timeseries_endpoints"]:
        docs: list[dict] = []
        cursor = datetime.combine(since, datetime.min.time())
        stop = datetime.combine(end, datetime.min.time())
        try:
            while cursor < stop:
                upper = min(cursor + chunk, stop)
                params = {"start_datetime": f"{cursor.isoformat()}Z", "end_datetime": f"{upper.isoformat()}Z"}
                docs.extend(client.paginate(f"/v2/usercollection/{ep}", params))
                cursor = upper
            write(ep, {"start_datetime": f"{since}T00:00:00Z", "end_datetime": f"{end}T00:00:00Z"}, docs)
        except OuraApiError as e:
            if e.status not in SKIPPABLE:
                raise
            skipped[ep] = str(e)

    for single in ("personal_info", "ring_configuration"):
        try:
            data = client.get(f"/v2/usercollection/{single}")
            write(single, {}, data.get("data", [data]) if isinstance(data, dict) else data)
        except OuraApiError as e:
            if e.status not in SKIPPABLE:
                raise
            skipped[single] = str(e)

    manifest = {
        "source": "oura",
        "pull_id": dest.name,
        "status": "complete",
        "pulled_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "window": {"start": since.isoformat(), "end": end.isoformat()},
        "requests": client.requests,
        "counts": counts,
        "skipped": skipped,
    }
    (dest / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    for f in dest.glob("*.json"):
        f.chmod(0o444)
    return manifest
