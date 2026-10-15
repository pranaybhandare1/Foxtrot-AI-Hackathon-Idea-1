# ontology/ (t1d-ontology)

`ontology.yaml` is the contract between the data and everything that uses it.

- **Object types:** primary key, typed properties with descriptions, backing clean dataset.
- **Datasets:** dense time series (e.g. `Glucose5Min`), queryable and linkable like objects.
- **Link types:** `{from: <Type>.<fk property>, to: <Type>}`.

On every build, `t1d_ontology.validation` checks that each backing dataset exists, that every declared property
is present with its type, that there are no undeclared columns, that primary keys are unique and non-null, and
that every foreign key resolves. Any failure stops the build. `t1d_ontology.publish` then writes DuckDB views
and `data/reports/ontology_catalog.md` (generated, with an ER diagram).

```python
from t1d_ontology.client import OntologyClient

ont = OntologyClient()
ont.objects("Meal").where("meal_slot = 'dinner' AND carbs_g >= ?", 40).search_around("meal_bolus").to_polars()
ont.objects("GlycemicExcursion").where("kind = 'hypo'").aggregate(n="count(*)", nadir="median(extreme_sg_mgdl)")
ont.get("Day", "2026-08-14")
ont.sql('SELECT set_day, avg(tir) FROM "Day" GROUP BY 1')
```

Types: `string · integer · double · boolean · date · timestamp`. Units go in the name suffix (`_mgdl`, `_u`, `_g`).
