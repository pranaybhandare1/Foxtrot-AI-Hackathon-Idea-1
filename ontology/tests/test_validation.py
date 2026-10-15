"""Ontology validation must catch contract violations: duplicate keys, wrong types, dangling links."""

from datetime import date
from pathlib import Path

import polars as pl
from t1d_core.settings import Config, Layers
from t1d_ontology.model import load
from t1d_ontology.validation import validate

TYPE_MAP = {
    "string": pl.Utf8,
    "integer": pl.Int64,
    "double": pl.Float64,
    "boolean": pl.Boolean,
    "date": pl.Date,
    "timestamp": pl.Datetime("us"),
}


def test_ontology_yaml_loads_and_links_are_consistent():
    ont = load()
    assert "Day" in ont.object_types and "meal_bolus" in ont.link_types
    for lt in ont.link_types.values():
        assert lt.foreign_key in ont.object_types[lt.many].properties


def test_validation_catches_bad_pk_type_and_dangling_link(tmp_path: Path):
    ont = load()
    cfg = Config(raw={}, layers=Layers(tmp_path))
    (tmp_path / "clean").mkdir()
    type_map = TYPE_MAP
    # write every backing dataset empty-but-typed, then corrupt a few
    for ot in ont.object_types.values():
        schema = {p.name: type_map[p.type] for p in ot.properties.values()}
        ot.path(tmp_path).parent.mkdir(parents=True, exist_ok=True)  # clean/ and writeback/
        pl.DataFrame(schema=schema).write_parquet(ot.path(tmp_path))
    day_schema = {p.name: type_map[p.type] for p in ont.object_types["Day"].properties.values()}
    pl.DataFrame({"date_local": [date(2026, 5, 1)] * 2}).with_columns(
        [pl.lit(None, dtype=t).alias(c) for c, t in day_schema.items() if c != "date_local"]
    ).select(list(day_schema)).write_parquet(ont.object_types["Day"].path(tmp_path))
    meal_schema = {p.name: type_map[p.type] for p in ont.object_types["Meal"].properties.values()}
    pl.DataFrame({"meal_id": ["m1"], "date_local": [date(2026, 6, 1)]}).with_columns(
        [pl.lit(None, dtype=t).alias(c) for c, t in meal_schema.items() if c not in ("meal_id", "date_local")]
    ).select(list(meal_schema)).with_columns(pl.col("carbs_g").cast(pl.Utf8)).write_parquet(
        ont.object_types["Meal"].path(tmp_path)
    )

    errors = "\n".join(validate(ont, cfg)["errors"])
    assert "Day: primary key date_local not unique" in errors
    assert "Meal.carbs_g: declared double, data is string" in errors
    assert "link day_meals: 1 Meal.date_local values not found in Day" in errors


def test_cross_source_links_may_be_unresolved(tmp_path: Path):
    """Oura nights after the latest pump export link to Days that don't exist yet: counted, not fatal."""
    ont = load()
    assert not ont.link_types["day_sleeps"].required and ont.link_types["day_meals"].required
    cfg = Config(raw={}, layers=Layers(tmp_path))
    for ot in ont.object_types.values():
        ot.path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(schema={p.name: TYPE_MAP[p.type] for p in ot.properties.values()}).write_parquet(ot.path(tmp_path))
    sleep = ont.object_types["SleepSession"]
    schema = {p.name: TYPE_MAP[p.type] for p in sleep.properties.values()}
    pl.DataFrame({"sleep_id": ["s1"], "date_local": [date(2026, 10, 1)]}).with_columns(
        [pl.lit(None, dtype=t).alias(c) for c, t in schema.items() if c not in ("sleep_id", "date_local")]
    ).select(list(schema)).write_parquet(sleep.path(tmp_path))
    result = validate(ont, cfg)
    assert not [e for e in result["errors"] if "day_sleeps" in e]
    assert result["links"]["day_sleeps"]["unresolved"] == 1
