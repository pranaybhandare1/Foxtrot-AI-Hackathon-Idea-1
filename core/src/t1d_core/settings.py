"""Repository-wide settings: where the repo, config, ontology and data lake live.

Everything that needs a path imports it from here, so moving a folder is a one-line change.
Set T1D_CONFIG to point at an alternative pipeline.yaml (e.g. in tests).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import yaml


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "config" / "pipeline.yaml").exists():
            return parent
    return Path.cwd()


REPO_ROOT = _find_repo_root()
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.yaml"
ONTOLOGY_FILE = REPO_ROOT / "ontology" / "ontology.yaml"


def parse_utc_offset(text: str) -> timedelta:
    """'-04:00' -> timedelta(hours=-4)."""
    sign = -1 if text.startswith("-") else 1
    hours, minutes = text.lstrip("+-").split(":")
    return sign * timedelta(hours=int(hours), minutes=int(minutes))


@dataclass(frozen=True)
class Layers:
    """Medallion layout under the data root: landing -> raw -> transformed -> clean (+ warehouse, reports)."""

    root: Path

    @property
    def landing(self) -> Path:
        return self.root / "landing"

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def transformed(self) -> Path:
        return self.root / "transformed"

    @property
    def clean(self) -> Path:
        return self.root / "clean"

    @property
    def writeback(self) -> Path:
        """User-authored objects created through ontology actions. Never rebuilt or deleted by the pipeline."""
        return self.root / "writeback"

    @property
    def warehouse(self) -> Path:
        return self.root / "warehouse.duckdb"

    @property
    def reports(self) -> Path:
        return self.root / "reports"


@dataclass(frozen=True)
class Config:
    raw: dict
    layers: Layers

    @property
    def reports_dir(self) -> Path:
        return self.layers.reports

    @property
    def carelink(self) -> dict:
        return self.raw["sources"]["carelink"]

    @property
    def analytics(self) -> dict:
        return self.raw["analytics"]


def load_config(path: Path | None = None) -> Config:
    path = path or Path(os.environ.get("T1D_CONFIG", DEFAULT_CONFIG))
    raw = yaml.safe_load(path.read_text())
    data_root = Path(raw["data_root"])
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root
    return Config(raw=raw, layers=Layers(data_root))
