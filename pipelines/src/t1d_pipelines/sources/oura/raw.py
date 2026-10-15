"""Oura raw layer: every landed document, faithfully, with lineage.

    raw/oura_documents.parquet   one row per (pull, endpoint, document): id, day, document (JSON text)
    raw/oura_heartrate.parquet   one row per heart-rate sample (the bulk endpoint, kept columnar)

Nothing is typed, deduplicated or dropped here; overlapping pulls are resolved in transformed.
`personal_info` is not carried forward (not needed for analysis, and it is personal data).
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from t1d_core.settings import Config

EXCLUDED = {"personal_info"}


def _pulls(cfg: Config) -> list[Path]:
    root = cfg.layers.landing / "oura"
    return sorted(p for p in root.glob("pull_*") if (p / "_manifest.json").exists()) if root.exists() else []


def build(cfg: Config) -> dict:
    docs: list[dict] = []
    hr_frames: list[pl.DataFrame] = []
    for pull in _pulls(cfg):
        manifest = json.loads((pull / "_manifest.json").read_text())
        if manifest.get("status") != "complete":
            continue
        for f in sorted(pull.glob("*.json")):
            if f.name.startswith("_") or f.stem in EXCLUDED:
                continue
            payload = json.loads(f.read_text())
            if f.stem == "heartrate":
                rows = payload["documents"]
                if rows:
                    hr_frames.append(
                        pl.DataFrame(
                            {
                                "timestamp": [r.get("timestamp") for r in rows],
                                "bpm": [r.get("bpm") for r in rows],
                                "source": [r.get("source") for r in rows],
                            },
                            schema={"timestamp": pl.Utf8, "bpm": pl.Int64, "source": pl.Utf8},
                        ).with_columns(pl.lit(pull.name).alias("pull_id"))
                    )
                continue
            for d in payload["documents"]:
                docs.append(
                    {
                        "pull_id": pull.name,
                        "endpoint": f.stem,
                        "id": str(d.get("id", "")),
                        "day": d.get("day"),
                        "document": json.dumps(d, separators=(",", ":")),
                    }
                )
    out = cfg.layers.raw
    out.mkdir(parents=True, exist_ok=True)
    schema = {"pull_id": pl.Utf8, "endpoint": pl.Utf8, "id": pl.Utf8, "day": pl.Utf8, "document": pl.Utf8}
    documents = pl.DataFrame(docs, schema=schema)
    hr = (
        pl.concat(hr_frames)
        if hr_frames
        else pl.DataFrame(schema={"timestamp": pl.Utf8, "bpm": pl.Int64, "source": pl.Utf8, "pull_id": pl.Utf8})
    )
    documents.write_parquet(out / "oura_documents.parquet")
    hr.write_parquet(out / "oura_heartrate.parquet")
    return {
        "pulls": len(_pulls(cfg)),
        "documents": documents.height,
        "heartrate_samples": hr.height,
        "by_endpoint": dict(documents.group_by("endpoint").len().sort("endpoint").iter_rows()),
    }
