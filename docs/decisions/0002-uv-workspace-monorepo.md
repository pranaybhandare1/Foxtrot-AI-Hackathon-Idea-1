# 0002: One repo, uv workspace, one package per concern

**Status:** accepted · 2026-09-26

## Context
Pipelines, the ontology, the API and the web UI evolve together but have different dependencies and
audiences. A new contributor must be able to find things quickly.

## Decision
A single repository with top-level folders by concern (`core/`, `pipelines/`, `ontology/`, `app/api`,
`app/web`), each a separately-declared package in a **uv workspace** with a shared lockfile. Node is
pinned through the `nodejs-wheel` dev dependency, so `uv sync` provides it. A `Makefile` is the single entry point.

## Consequences
- Package boundaries make dependency direction explicit (core ← ontology ← pipelines / api).
- One `make setup` and no system-wide installs.
- Slightly more pyproject files than a single package.
