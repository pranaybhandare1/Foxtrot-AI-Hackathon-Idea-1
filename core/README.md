# core/ (t1d-core)

Shared settings used by every Python package: repo root discovery, `config/pipeline.yaml` loading
(`T1D_CONFIG` overrides the path), and the medallion layer layout under `data/`.

```python
from t1d_core.settings import load_config

cfg = load_config()
cfg.layers.clean  # Path to data/clean
cfg.carelink["home_timezone"]
```
Keep this package tiny and dependency-free (PyYAML only).
