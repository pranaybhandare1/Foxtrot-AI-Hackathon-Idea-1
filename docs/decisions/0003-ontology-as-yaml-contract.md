# 0003: The ontology is a YAML contract validated on every build

**Status:** accepted · 2026-09-26

## Context
We want Foundry-style ontology semantics (object types, links, search-around) without a platform.
Options considered: RDF/OWL (heavy, poor fit for analytics), LinkML (good, but adds a toolchain),
a graph database (extra runtime), or a plain declarative spec on top of the lakehouse.

## Decision
`ontology/ontology.yaml` declares object types (primary key, typed properties, backing dataset),
dense datasets, and link types (via foreign-key properties). The build validates data against it
(keys, types, undeclared columns, dangling links) and fails on drift. It publishes DuckDB views and a
generated catalog. A small Python client provides object sets, filters and search-around. The API
exposes the same metadata to power a generic explorer.

## Consequences
- The ontology is the reviewed source of truth, and schema drift is caught at build time.
- It can later be compiled to LinkML / JSON Schema if interoperability is needed.
- There are no write-back "actions" yet. Those will be added when the decision-support layer needs them.
