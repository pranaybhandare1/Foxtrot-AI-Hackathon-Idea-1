"""A small OSDK-style client over the ontology: object sets, filters, search-around, SQL.

    from t1d_ontology.client import OntologyClient
    ont = OntologyClient()
    big_dinners = ont.objects("Meal").where("meal_slot = 'dinner' AND carbs_g >= 40")
    big_dinners.count()
    big_dinners.search_around("meal_bolus").to_polars()          # Meal -> Bolus
    ont.objects("CgmSensor").where("wear_days < 13").search_around("sensor_excursions")
    ont.get("Day", "2026-07-04")
    ont.sql('SELECT meal_slot, median(rise_to_peak_mgdl) FROM "Meal" GROUP BY 1')

Object sets are lazy SQL over the Parquet-backed views; nothing runs until you ask for data.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import polars as pl
from t1d_core.settings import Config, load_config

from t1d_ontology.actions import ensure_tables
from t1d_ontology.edits import refresh_views
from t1d_ontology.model import Ontology, load


class OntologyClient:
    def __init__(self, cfg: Config | None = None, ontology: Ontology | None = None):
        self.cfg = cfg or load_config()
        self.ontology = ontology or load()
        self.con = duckdb.connect()
        ensure_tables(self.ontology, self.cfg)  # write-back tables may not exist yet on a fresh checkout
        refresh_views(self.con, self.ontology, self.cfg)

    def objects(self, type_name: str) -> ObjectSet:
        if type_name not in self.ontology.object_types:
            raise KeyError(f"Unknown object type {type_name!r}; have {sorted(self.ontology.object_types)}")
        return ObjectSet(self, type_name, f'SELECT * FROM "{type_name}"')

    def get(self, type_name: str, primary_key) -> dict | None:
        pk = self.ontology.object_types[type_name].primary_key
        rows = self.objects(type_name).where(f"{pk} = ?", primary_key).to_polars()
        return rows.row(0, named=True) if rows.height else None

    def sql(self, query: str, params: list | None = None) -> pl.DataFrame:
        return self.con.execute(query, params or []).pl()

    def describe(self, type_name: str) -> pl.DataFrame:
        ot = self.ontology.object_types[type_name]
        return pl.DataFrame(
            [{"property": p.name, "type": p.type, "description": p.description} for p in ot.properties.values()]
        )


@dataclass(frozen=True)
class ObjectSet:
    client: OntologyClient
    type_name: str
    query: str
    params: tuple = ()

    def _wrap(self, sql: str, params: tuple = ()) -> ObjectSet:
        return ObjectSet(self.client, self.type_name, sql, self.params + params)

    def where(self, predicate: str, *params) -> ObjectSet:
        """SQL predicate over this type's properties, e.g. where("carbs_g >= ?", 40)."""
        return self._wrap(f"SELECT * FROM ({self.query}) WHERE {predicate}", params)

    def order_by(self, *columns: str, desc: bool = False) -> ObjectSet:
        return self._wrap(f"SELECT * FROM ({self.query}) ORDER BY {', '.join(columns)}{' DESC' if desc else ''}")

    def limit(self, n: int) -> ObjectSet:
        return self._wrap(f"SELECT * FROM ({self.query}) LIMIT {int(n)}")

    def search_around(self, link_name: str) -> ObjectSet:
        """Follow a link type to the objects on its other side."""
        link = self.client.ontology.link_types[link_name]
        types = self.client.ontology.object_types
        if self.type_name == link.many:
            target = link.one
            sql = (
                f'SELECT * FROM "{target}" WHERE {types[target].primary_key} IN '
                f"(SELECT {link.foreign_key} FROM ({self.query}))"
            )
        elif self.type_name == link.one:
            target = link.many
            sql = (
                f'SELECT * FROM "{target}" WHERE {link.foreign_key} IN '
                f"(SELECT {types[self.type_name].primary_key} FROM ({self.query}))"
            )
        else:
            raise ValueError(f"Link {link_name} does not touch {self.type_name}")
        return ObjectSet(self.client, target, sql, self.params)

    def to_polars(self) -> pl.DataFrame:
        return self.client.con.execute(self.query, list(self.params)).pl()

    def count(self) -> int:
        return self.client.con.execute(f"SELECT count(*) FROM ({self.query})", list(self.params)).fetchone()[0]

    def aggregate(self, **metrics: str) -> dict:
        """aggregate(n='count(*)', tir='avg(tir)') -> {'n': ..., 'tir': ...}"""
        cols = ", ".join(f"{expr} AS {name}" for name, expr in metrics.items())
        return self.client.con.execute(f"SELECT {cols} FROM ({self.query})", list(self.params)).pl().row(0, named=True)
