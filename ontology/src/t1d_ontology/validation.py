"""Validate backing datasets against the ontology contract.

Checks, per object type: backing dataset exists; every declared property exists with the
declared type; no undeclared columns; primary key non-null and unique. Per link type: every
non-null foreign key resolves to an object on the other side (links declared `required: false`
only report how many keys are unresolved).
"""

from __future__ import annotations

import polars as pl
from t1d_core.settings import Config

from t1d_ontology.model import Ontology, polars_to_ontology_type


class OntologyValidationError(RuntimeError):
    pass


def validate(ont: Ontology, cfg: Config) -> dict:
    errors: list[str] = []
    rows: dict[str, int] = {}
    pks: dict[str, pl.Series] = {}
    frames: dict[str, pl.DataFrame] = {}
    for ot in ont.object_types.values():
        path = ot.path(cfg.layers.root)
        if not path.exists():
            errors.append(f"{ot.name}: backing dataset {path} missing")
            continue
        df = pl.read_parquet(path)
        frames[ot.name], rows[ot.name] = df, df.height
        if ot.optional and df.height == 0:
            pks[ot.name] = pl.Series(ot.primary_key, [], dtype=pl.Utf8)
            continue  # optional source not connected: nothing to validate
        actual = {c: polars_to_ontology_type(t) for c, t in df.schema.items()}
        for p in ot.properties.values():
            if p.name not in actual:
                errors.append(f"{ot.name}.{p.name}: declared but missing from {ot.backing_dataset}")
            elif actual[p.name] != p.type:
                errors.append(f"{ot.name}.{p.name}: declared {p.type}, data is {actual[p.name]}")
        for c in actual.keys() - ot.properties.keys():
            errors.append(f"{ot.name}.{c}: column in {ot.backing_dataset} not declared in the ontology")
        pk = df[ot.primary_key]
        if pk.null_count():
            errors.append(f"{ot.name}: {pk.null_count()} null primary keys")
        if pk.n_unique() != df.height:
            errors.append(f"{ot.name}: primary key {ot.primary_key} not unique ({df.height - pk.n_unique()} dupes)")
        pks[ot.name] = pk

    link_stats = {}
    for lt in ont.link_types.values():
        if lt.many not in frames or lt.one not in pks:
            continue
        fk = frames[lt.many][lt.foreign_key].drop_nulls()
        dangling = fk.filter(~fk.is_in(pks[lt.one].implode()))
        link_stats[lt.name] = {
            "linked": fk.len() - dangling.len(),
            "null_fk": frames[lt.many][lt.foreign_key].null_count(),
            "unresolved": dangling.len(),
        }
        if dangling.len() and lt.required:
            errors.append(
                f"link {lt.name}: {dangling.len()} {lt.many}.{lt.foreign_key} values not found in "
                f"{lt.one} (e.g. {dangling.unique().head(3).to_list()})"
            )
    return {"errors": errors, "rows": rows, "links": link_stats}
