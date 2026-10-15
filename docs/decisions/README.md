# Architecture decision records

Short records of decisions that shape the codebase: context, the decision, and its consequences.
Add a new numbered file when you make a choice a future contributor would otherwise have to reverse-engineer.

| # | Decision |
|---|---|
| [0001](0001-local-medallion-lakehouse.md) | Local medallion lakehouse on Parquet + DuckDB |
| [0002](0002-uv-workspace-monorepo.md) | One repo, uv workspace, one package per concern |
| [0003](0003-ontology-as-yaml-contract.md) | The ontology is a YAML contract validated on every build |
| [0004](0004-pump-clock-reconstruction.md) | Reconstruct UTC from pump clock changes |
| [0005](0005-web-stack.md) | FastAPI + React/TypeScript + ECharts for the app |
| [0006](0006-writeback-actions.md) | Write-back only through typed ontology actions, stored outside the rebuilt layers |
