"""Three ways into the data. Run: `make quickstart` (or `uv run python examples/quickstart.py`)."""

import duckdb
import polars as pl
from t1d_ontology.client import OntologyClient

# 1) The ontology SDK: object sets, filters and search-around over the clean Parquet
ont = OntologyClient()
print("Object types:", ", ".join(ont.ontology.object_types))
big_dinners = ont.objects("Meal").where("meal_slot = 'dinner' AND carbs_g >= 60")
print("Big dinners:", big_dinners.count(), "· their boluses:", big_dinners.search_around("meal_bolus").count())

# 2) SQL over the ontology views (same names as the object types)
print(ont.sql("""
    SELECT date_trunc('month', date_local) AS month, round(avg(tir), 3) AS tir, round(avg(tdd_u), 1) AS tdd_u
    FROM "Day" WHERE is_valid_cgm_day GROUP BY 1 ORDER BY 1
"""))

# Cross-pillar: sleep the night before vs. the day's time in range
print(ont.sql("""
    SELECT CASE WHEN o.total_sleep_min < 390 THEN '< 6.5 h' WHEN o.total_sleep_min >= 450 THEN '>= 7.5 h' ELSE 'between' END AS sleep,
           count(*) AS days, round(avg(d.tir), 3) AS tir
    FROM "Day" d JOIN "OuraDay" o USING (date_local) WHERE d.is_valid_cgm_day GROUP BY 1 ORDER BY 1
"""))

# 3) The portable DuckDB file: plain tables, works in any DuckDB client / notebook / BI tool
con = duckdb.connect("data/ontology.duckdb", read_only=True)
print(con.sql('SELECT kind, level, count(*) AS n, round(avg(duration_min)) AS avg_min FROM "GlycemicExcursion" GROUP BY ALL ORDER BY n DESC'))

# Or straight Parquet with polars
meals = pl.read_parquet("data/clean/meal.parquet")
print(meals.group_by("meal_slot").agg(pl.len(), pl.col("rise_to_peak_mgdl").median()).sort("meal_slot"))
