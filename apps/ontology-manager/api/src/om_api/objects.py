"""Objects: browse any object type (filter, search, sort), open one and follow its links.

Dynamic SQL is built only from names that exist in ontology.yaml; all values are bound parameters.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from om_api.db import SQL_TYPES, client, cursor, query, records
from om_api.ontology_routes import object_type

router = APIRouter(tags=["objects"])
SQL_OPS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
OPS = set(SQL_OPS) | {"contains", "isnull", "notnull"}


def where_clause(ot, filters: list[tuple[str, str, object]], q: str | None = None) -> tuple[str, list]:
    """filters: (property, op, value). Raises ValueError on unknown properties or operators."""
    clauses, params = ["TRUE"], []
    for col, op, value in filters:
        if col not in ot.properties or op not in OPS:
            raise ValueError(f"bad filter {col} {op}")
        if op == "isnull":
            clauses.append(f'"{col}" IS NULL')
        elif op == "notnull":
            clauses.append(f'"{col}" IS NOT NULL')
        elif op == "contains":
            clauses.append(f'CAST("{col}" AS VARCHAR) ILIKE ?')
            params.append(f"%{value}%")
        else:
            clauses.append(f'"{col}" {SQL_OPS[op]} TRY_CAST(? AS {SQL_TYPES[ot.properties[col].type]})')
            params.append(None if value is None else str(value))
    if q:
        strings = [p.name for p in ot.properties.values() if p.type == "string"]
        if strings:
            clauses.append("(" + " OR ".join(f'"{c}" ILIKE ?' for c in strings) + ")")
            params += [f"%{q}%"] * len(strings)
    return " AND ".join(clauses), params


def parse_filters(specs: list[str]) -> list[tuple[str, str, object]]:
    out = []
    for spec in specs:
        parts = spec.split(":", 2)
        if len(parts) < 2:
            raise HTTPException(400, f"bad filter {spec!r}; use property:op:value")
        out.append((parts[0], parts[1], parts[2] if len(parts) > 2 else None))
    return out


@router.get("/objects/{type_name}")
def list_objects(
    type_name: str,
    filter: list[str] = Query(default=[]),
    q: str | None = None,
    order_by: str | None = None,
    desc: bool = True,
    limit: int = Query(500, le=20000),
    offset: int = Query(0, ge=0),
    cur=Depends(cursor),
) -> dict:
    ot = object_type(type_name)
    try:
        where, params = where_clause(ot, parse_filters(filter), q)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    order = order_by if order_by in ot.properties else (ot.title if ot.title in ot.properties else ot.primary_key)
    total = cur.execute(f'SELECT count(*) FROM "{ot.name}" WHERE {where}', params).fetchone()[0]
    rows = query(
        cur,
        f'SELECT * FROM "{ot.name}" WHERE {where} ORDER BY "{order}" {"DESC" if desc else "ASC"} '
        f"NULLS LAST LIMIT {int(limit)} OFFSET {int(offset)}",
        params,
    )
    return {"total": total, "rows": records(rows), "order_by": order, "desc": desc}


def object_with_links(cur, ot, pk: str, link_limit: int = 200) -> dict:
    pk_type = SQL_TYPES[ot.properties[ot.primary_key].type]
    found = records(query(cur, f'SELECT * FROM "{ot.name}" WHERE "{ot.primary_key}" = TRY_CAST(? AS {pk_type})', [pk]))
    if not found:
        raise HTTPException(404, f"{ot.name} {pk} not found")
    obj = found[0]
    ont = client().ontology
    links = []
    for lt in ont.links_of(ot.name):
        if lt.many == ot.name:  # this object -> the one it points to
            target = ont.object_types[lt.one]
            key = obj.get(lt.foreign_key)
            rows = [] if key is None else records(
                query(cur, f'SELECT * FROM "{target.name}" WHERE "{target.primary_key}" = ?', [key])
            )  # fmt: skip
            links.append(
                {"link": lt.name, "target": target.name, "cardinality": "one", "total": len(rows), "rows": rows}
            )
        else:  # the many objects pointing at this one
            target = ont.object_types[lt.many]
            total = cur.execute(
                f'SELECT count(*) FROM "{target.name}" WHERE "{lt.foreign_key}" = ?', [obj[ot.primary_key]]
            ).fetchone()[0]
            order = target.title if target.title in target.properties else target.primary_key
            rows = records(
                query(
                    cur,
                    f'SELECT * FROM "{target.name}" WHERE "{lt.foreign_key}" = ? ORDER BY "{order}" LIMIT {int(link_limit)}',
                    [obj[ot.primary_key]],
                )
            )
            links.append({"link": lt.name, "target": target.name, "cardinality": "many", "total": total, "rows": rows})
    return {"type": ot.name, "primary_key": ot.primary_key, "object": obj, "links": links}


@router.get("/objects/{type_name}/{pk}")
def get_object(type_name: str, pk: str, cur=Depends(cursor)) -> dict:
    return object_with_links(cur, object_type(type_name), pk)
