"""End-to-end: run the whole pipeline on the real export (skipped if the export isn't on this machine)."""

import json
import shutil
from pathlib import Path

import pytest
from t1d_core.settings import Config, Layers, load_config
from t1d_ontology.client import OntologyClient
from t1d_pipelines.cli import _run_layer
from t1d_pipelines.quality import checks
from t1d_pipelines.sources.carelink import landing

REAL = load_config()


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Config:
    if not Path(REAL.carelink["source_dir"]).exists():
        pytest.skip("CareLink export not available")
    root = tmp_path_factory.mktemp("lake")
    cfg = Config(raw=REAL.raw, layers=Layers(root / "data"))
    oura_landing = REAL.layers.landing / "oura"
    if oura_landing.exists():  # reuse real Oura pulls (no network in tests)
        shutil.copytree(oura_landing, cfg.layers.landing / "oura")
    for layer in ("landing", "raw", "transformed", "clean", "ontology"):
        _run_layer(layer, cfg)
    return cfg


def test_landing_is_idempotent(built):
    assert landing.land(built)["status"] == "unchanged"


def test_quality_has_no_failing_errors(built):
    result = checks.run(built)
    assert result["failed"] == [], result


def test_known_facts_about_this_export(built):
    stats = json.loads((built.layers.clean / "_build_stats.json").read_text())
    # history only grows with new exports: lower bounds from the first export (2026-09-26)
    assert stats["rows"]["cgm_sensor"] >= 17
    assert stats["rows"]["day"] >= 230
    ont = OntologyClient(cfg=built)
    first = ont.objects("CgmSensor").order_by("first_paired_utc").limit(1).to_polars().row(0, named=True)
    assert first["sensor_id"] == "0Q4HRYM13"
    # Europe trip: pump was on UTC+2 in mid August
    assert ont.get("Day", "2026-08-14")["utc_offset_min"] == 120


def test_ontology_client_search_around(built):
    ont = OntologyClient(cfg=built)
    big = ont.objects("Meal").where("carbs_g >= ?", 40)
    boluses = big.search_around("meal_bolus")
    assert 0 < boluses.count() <= big.count()
    assert (
        ont.objects("CgmSensor").search_around("sensor_readings").count()
        == ont.objects("GlucoseReading").where("sensor_id IS NOT NULL").count()
    )
