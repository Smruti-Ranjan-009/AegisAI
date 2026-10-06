# AegisAI feature engineering

This Python 3.12 package implements Phase 4's offline, deterministic conversion
of validated Phase 1 OTLP captures into service-window and metric-window
Parquet datasets. It does not train, evaluate, or serve models.

From the repository root:

```powershell
python -m pip install -e "ml\feature_engineering[test]"
python -m aegis_features.cli inspect --run <run-id>
python -m aegis_features.cli build --run <run-id> --window-seconds 60
python -m aegis_features.cli validate --dataset <dataset-id>
python -m aegis_features.cli summary --dataset <dataset-id>
```

See `docs/feature-engineering.md` for contracts, quality gates, and complete
usage instructions.
