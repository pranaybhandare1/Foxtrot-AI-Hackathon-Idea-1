"""Ontology actions: typed parameter validation and atomic write-back into data/writeback/."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from t1d_core.settings import Config, Layers
from t1d_ontology.actions import ActionError, apply, ensure_tables
from t1d_ontology.model import load


@pytest.fixture
def env(tmp_path: Path):
    return load(), Config(raw={}, layers=Layers(tmp_path))


def test_model_parses_groups_display_and_action_types(env):
    ont, _ = env
    assert ont.object_types["Meal"].group == "insulin_meals" and ont.object_types["Meal"].sources == ("carelink",)
    assert {"create_experiment", "update_experiment", "add_day_note"} <= ont.action_types.keys()
    assert all(t.group in ont.groups for t in ont.object_types.values() if t.group)


def test_ensure_tables_creates_typed_empty_writeback_tables(env):
    ont, cfg = env
    ensure_tables(ont, cfg)
    df = pl.read_parquet(cfg.layers.writeback / "experiment.parquet")
    assert df.height == 0 and df.schema["start_date"] == pl.Date


def test_create_then_modify_experiment(env):
    ont, cfg = env
    params = {
        "title": "Pre-bolus",
        "metric": "meal_rise",
        "better": "lower",
        "start_date": "2026-10-01",
        "end_date": "2026-10-14",
    }
    created = apply(ont, cfg, "create_experiment", params)
    pk = created["primary_key"]
    assert created["object"]["status"] == "active" and created["object"]["start_date"] == date(2026, 10, 1)
    updated = apply(ont, cfg, "update_experiment", {"experiment_id": pk, "status": "completed", "notes": "worked"})
    assert updated["object"]["status"] == "completed" and updated["object"]["notes"] == "worked"
    df = pl.read_parquet(cfg.layers.writeback / "experiment.parquet")
    assert df.height == 1 and df["status"][0] == "completed"


@pytest.mark.parametrize(
    "action, params, message",
    [
        ("create_experiment", {"title": "x"}, "required"),
        (
            "create_experiment",
            {"title": "x", "metric": "bogus", "better": "lower", "start_date": "2026-10-01", "end_date": "2026-10-02"},
            "one of",
        ),
        (
            "create_experiment",
            {"title": "x", "metric": "tir", "better": "higher", "start_date": "2026-10-05", "end_date": "2026-10-01"},
            "before",
        ),
        ("add_day_note", {"date_local": "not-a-date", "text": "hi"}, "expected date"),
        ("add_day_note", {"date_local": "2026-10-01", "text": "hi", "extra": 1}, "unknown parameters"),
        ("update_experiment", {"experiment_id": "missing", "status": "completed"}, "not found"),
        ("drop_tables", {}, "unknown action"),
    ],
)
def test_invalid_actions_are_rejected(env, action, params, message):
    ont, cfg = env
    with pytest.raises(ActionError, match=message):
        apply(ont, cfg, action, params)
