"""Ontology model: groups, object types, datasets, link types and action types, from ontology/ontology.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
import yaml
from t1d_core.settings import ONTOLOGY_FILE

TYPES = {"string", "integer", "double", "boolean", "date", "timestamp"}


def polars_to_ontology_type(dtype: pl.DataType) -> str:
    if dtype == pl.String:
        return "string"
    if dtype.is_integer():
        return "integer"
    if dtype.is_float():
        return "double"
    if dtype == pl.Boolean:
        return "boolean"
    if dtype == pl.Date:
        return "date"
    if isinstance(dtype, pl.Datetime):
        return "timestamp"
    return f"unsupported:{dtype}"


@dataclass(frozen=True)
class Property:
    name: str
    type: str
    description: str = ""


@dataclass(frozen=True)
class ObjectType:
    name: str
    description: str
    backing_dataset: str  # relative to data root, e.g. clean/day
    primary_key: str
    properties: dict[str, Property]
    title: str | None = None
    is_dataset: bool = False  # dense time series: queryable + linkable, not an "object"
    optional: bool = False  # from an optional source: an empty backing table is valid as-is
    group: str | None = None  # Ontology Manager grouping (see `groups`)
    icon: str = "cube"
    color: str = "#64748b"
    sources: tuple[str, ...] = ()  # upstream systems: carelink, oura, writeback

    def path(self, data_root: Path) -> Path:
        return data_root / f"{self.backing_dataset}.parquet"


@dataclass(frozen=True)
class LinkType:
    name: str
    many: str  # object type holding the foreign key
    foreign_key: str
    one: str  # object type whose primary key is referenced
    required: bool = True  # False: unresolved keys are allowed (cross-source link, target may lag)


@dataclass(frozen=True)
class Group:
    name: str
    display_name: str
    description: str = ""


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    required: bool = False
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionType:
    """A typed write to the ontology (Foundry "action"): `create` makes an object, `modify` edits one."""

    name: str
    display_name: str
    description: str
    kind: str  # create | modify
    object_type: str
    parameters: dict[str, Parameter]


@dataclass
class Ontology:
    name: str
    version: int
    object_types: dict[str, ObjectType] = field(default_factory=dict)
    link_types: dict[str, LinkType] = field(default_factory=dict)
    groups: dict[str, Group] = field(default_factory=dict)
    action_types: dict[str, ActionType] = field(default_factory=dict)

    def links_of(self, type_name: str) -> list[LinkType]:
        return [lt for lt in self.link_types.values() if type_name in (lt.many, lt.one)]


def load(path: Path = ONTOLOGY_FILE) -> Ontology:
    spec = yaml.safe_load(path.read_text())
    ont = Ontology(name=spec["ontology"], version=spec["version"])
    for name, g in (spec.get("groups") or {}).items():
        ont.groups[name] = Group(name, g.get("display_name", name), g.get("description", ""))
    for section, is_dataset in (("object_types", False), ("datasets", True)):
        for name, ot in (spec.get(section) or {}).items():
            props = {p: Property(p, v["type"], v.get("description", "")) for p, v in ot["properties"].items()}
            bad = {p.name: p.type for p in props.values() if p.type not in TYPES}
            if bad:
                raise ValueError(f"{name}: unknown property types {bad}")
            if ot["primary_key"] not in props:
                raise ValueError(f"{name}: primary key {ot['primary_key']} is not a declared property")
            ont.object_types[name] = ObjectType(
                name=name,
                description=" ".join(ot.get("description", "").split()),
                backing_dataset=ot["backing_dataset"],
                primary_key=ot["primary_key"],
                properties=props,
                title=ot.get("title"),
                is_dataset=is_dataset,
                optional=bool(ot.get("optional", False)),
                **_display(name, ot, ont),
            )
    for name, lt in (spec.get("link_types") or {}).items():
        many, fk = lt["from"].split(".")
        link = LinkType(name=name, many=many, foreign_key=fk, one=lt["to"], required=bool(lt.get("required", True)))
        for t in (link.many, link.one):
            if t not in ont.object_types:
                raise ValueError(f"link {name}: unknown object type {t}")
        if fk not in ont.object_types[many].properties:
            raise ValueError(f"link {name}: {many} has no property {fk}")
        ont.link_types[name] = link
    for name, at in (spec.get("action_types") or {}).items():
        if at["object_type"] not in ont.object_types:
            raise ValueError(f"action {name}: unknown object type {at['object_type']}")
        if at["kind"] not in ("create", "modify"):
            raise ValueError(f"action {name}: kind must be create or modify")
        params = {}
        for p, v in (at.get("parameters") or {}).items():
            if v["type"] not in TYPES:
                raise ValueError(f"action {name}: parameter {p} has unknown type {v['type']}")
            params[p] = Parameter(p, v["type"], bool(v.get("required", False)), tuple(v.get("enum", ())))
        ont.action_types[name] = ActionType(
            name=name,
            display_name=at.get("display_name", name),
            description=" ".join(at.get("description", "").split()),
            kind=at["kind"],
            object_type=at["object_type"],
            parameters=params,
        )
    return ont


def _display(name: str, ot: dict, ont: Ontology) -> dict:
    d = ot.get("display") or {}
    group = d.get("group")
    if group is not None and ont.groups and group not in ont.groups:
        raise ValueError(f"{name}: unknown group {group}")
    out = {"group": group, "sources": tuple(ot.get("sources") or ())}
    out |= {k: d[k] for k in ("icon", "color") if k in d}
    return out
