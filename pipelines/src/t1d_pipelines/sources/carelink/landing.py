"""Landing: copy a CareLink export batch into the lake, byte-for-byte, after verifying checksums.

A batch is immutable once landed. Re-running with the same files is a no-op; a
new export (new files or changed bytes) becomes a new batch. Downstream layers
dedupe events across overlapping batches.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from t1d_core.settings import Config


class ChecksumMismatch(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_checksums(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            out[name.strip().lstrip("*")] = digest
    return out


def _batch_id(source_dir: Path, files: list[Path]) -> str:
    """Name the batch by export date.

    The README's 'Exported from CareLink on YYYY-MM-DD' wins only if it is later than every file's window end;
    once newer exports are dropped into the folder, the README is stale, so the batch is named for the day
    after the newest window instead (an export always covers up to the day before it was made).
    """
    ends = [m.group(1) for f in files if (m := re.search(r"_to_(\d{4}-\d{2}-\d{2})", f.name))]
    after_newest = (date.fromisoformat(max(ends)) + timedelta(days=1)).isoformat() if ends else None
    readme = source_dir / "README.txt"
    if readme.exists():
        m = re.search(r"Exported from CareLink on (\d{4}-\d{2}-\d{2})", readme.read_text())
        if m and (after_newest is None or m.group(1) >= after_newest):
            return f"export_{m.group(1)}"
    if after_newest is None:
        raise ValueError(
            f"Cannot date this export: no README export date and no _to_YYYY-MM-DD in file names in {source_dir}"
        )
    return f"export_{after_newest}"


def land(cfg: Config) -> dict:
    src = Path(cfg.carelink["source_dir"])
    files = sorted(src.glob(cfg.carelink["file_glob"]))
    if not files:
        raise FileNotFoundError(f"No CareLink exports matching {cfg.carelink['file_glob']} in {src}")

    expected = _read_checksums(src / cfg.carelink["checksum_file"])
    missing = sorted(set(expected) - {f.name for f in files})
    if missing:
        raise ChecksumMismatch(f"Files listed in checksums but absent: {missing}")

    entries = []
    for f in files:
        digest = sha256(f)
        if f.name in expected and expected[f.name] != digest:
            raise ChecksumMismatch(f"{f.name}: expected {expected[f.name]}, got {digest}")
        entries.append(
            {"file": f.name, "sha256": digest, "bytes": f.stat().st_size, "checksum_verified": f.name in expected}
        )

    batch_id = _batch_id(src, files)
    dest = cfg.layers.landing / "carelink" / batch_id
    manifest_path = dest / "_manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        if {e["file"]: e["sha256"] for e in old["files"]} == {e["file"]: e["sha256"] for e in entries}:
            return old | {"status": "unchanged"}
        raise ChecksumMismatch(f"Batch {batch_id} already landed with different bytes; refusing to overwrite")

    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, dest / f.name)
    for extra in ("README.txt", cfg.carelink["checksum_file"]):
        if (src / extra).exists():
            shutil.copy2(src / extra, dest / extra)
    for f in dest.glob("*.csv"):
        f.chmod(0o444)

    manifest = {
        "source": "carelink",
        "batch_id": batch_id,
        "source_dir": str(src),
        "landed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest | {"status": "landed"}


def landed_batches(cfg: Config) -> list[Path]:
    root = cfg.layers.landing / "carelink"
    return sorted(p for p in root.glob("export_*") if (p / "_manifest.json").exists())
