"""Raw layer: parse landed CareLink CSVs into Parquet, faithfully.

Rules for this layer:
- Every source data row becomes exactly one output row; nothing is dropped, typed or fixed.
- All values stay strings with the original column names ('' becomes null).
- Every row carries lineage: batch, file, line number, section and the export's Index.
- Patient-identifying header fields (name, DOB, patient/system IDs) are not carried forward.

A CareLink export file is: 3 metadata lines, then three sections, each introduced by a
'-------,<device>,<Pump|Sensor>,<serial>,<label>' line and its own header row:
  pump                          -> discrete pump events (boluses, alerts, suspends, ...)
  pump_aggregated_auto_insulin  -> one row per day of SmartGuard auto insulin
  sensor                        -> CGM readings and sensor exceptions
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import polars as pl
from t1d_core.settings import Config

from t1d_pipelines.sources.carelink.landing import landed_batches

SECTION_NAMES = {
    ("Pump", "-------"): "pump",
    ("Pump", "Aggregated Auto Insulin Data"): "pump_aggregated_auto_insulin",
    ("Sensor", "-------"): "sensor",
}
PII_FIELDS = {"Last Name", "First Name", "Patient ID", "System ID", "Patient DOB"}


class RawParseError(RuntimeError):
    pass


def _parse_metadata(lines: list[str]) -> dict:
    rows = [next(csv.reader([ln])) for ln in lines[:3]]
    meta: dict[str, str] = {}
    for key, value in zip(rows[0][:6], rows[1][:6], strict=False):
        meta[key] = value
    for row in rows:
        tail = row[6:]
        i = 0
        while i < len(tail):
            key = tail[i].strip()
            if not key:
                i += 1
                continue
            if key == "CGM":  # may list several sensors: CGM,Guardian™ 4,Instinct
                meta[key] = "|".join(v for v in tail[i + 1 :] if v)
                break
            meta[key] = tail[i + 1] if i + 1 < len(tail) else ""
            i += 2
    return {k: v for k, v in meta.items() if k not in PII_FIELDS}


def parse_file(path: Path, batch_id: str, file_sha256: str) -> tuple[pl.DataFrame, dict]:
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    lines = text.splitlines()
    meta = _parse_metadata(lines)

    records: list[dict] = []
    section = header = None
    counts: dict[str, int] = {}
    for lineno, line in enumerate(lines, start=1):
        if lineno <= 3 or not line.strip():
            continue
        if line.startswith("-------"):
            parts = [p.strip() for p in line.split(",")]
            key = (parts[2], parts[4])
            if key not in SECTION_NAMES:
                raise RawParseError(f"{path.name}:{lineno}: unknown section marker {line!r}")
            section, header = SECTION_NAMES[key], None
            continue
        if line.startswith("Index,Date,Time"):
            header = next(csv.reader([line]))
            continue
        if section is None or header is None:
            raise RawParseError(f"{path.name}:{lineno}: data row outside a section")
        values = next(csv.reader([line]))
        if len(values) != len(header):
            raise RawParseError(f"{path.name}:{lineno}: {len(values)} fields, header has {len(header)}")
        rec = {h: (v if v != "" else None) for h, v in zip(header, values, strict=True)}
        rec.update(
            _batch_id=batch_id, _source_file=path.name, _source_line=lineno, _file_sha256=file_sha256, _section=section
        )
        records.append(rec)
        counts[section] = counts.get(section, 0) + 1

    file_meta = {
        "batch_id": batch_id,
        "source_file": path.name,
        "file_sha256": file_sha256,
        "has_bom": data.startswith(b"\xef\xbb\xbf"),
        "line_endings": "CRLF" if b"\r\n" in data else "LF",
        "n_lines": len(lines),
        "rows_pump": counts.get("pump", 0),
        "rows_pump_aggregated_auto_insulin": counts.get("pump_aggregated_auto_insulin", 0),
        "rows_sensor": counts.get("sensor", 0),
        **{k.lower().replace(" ", "_"): v for k, v in meta.items()},
    }
    schema = {c: pl.Utf8 for c in header} | {
        "_batch_id": pl.Utf8,
        "_source_file": pl.Utf8,
        "_source_line": pl.Int64,
        "_file_sha256": pl.Utf8,
        "_section": pl.Utf8,
    }
    return pl.DataFrame(records, schema=schema), file_meta


def build(cfg: Config) -> dict:
    frames, metas = [], []
    for batch_dir in landed_batches(cfg):
        manifest = json.loads((batch_dir / "_manifest.json").read_text())
        for entry in manifest["files"]:
            df, meta = parse_file(batch_dir / entry["file"], manifest["batch_id"], entry["sha256"])
            frames.append(df)
            metas.append(meta)
    events = pl.concat(frames, how="vertical")
    metadata = pl.DataFrame(metas, infer_schema_length=None)

    out = cfg.layers.raw
    out.mkdir(parents=True, exist_ok=True)
    events.write_parquet(out / "carelink_events.parquet")
    metadata.write_parquet(out / "carelink_file_metadata.parquet")
    return {
        "rows": events.height,
        "files": metadata.height,
        "rows_by_section": dict(events.group_by("_section").len().iter_rows()),
    }
