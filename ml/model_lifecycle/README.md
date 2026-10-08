# AegisAI model lifecycle

Phase 7 wraps the frozen Phase 5 anomaly detector and Phase 6 incident
classifier with local MLflow experiment tracking, registry versions, integrity
metadata, and candidate/champion aliases. It does not train, tune, or serve a
model.

Install this package alongside the two trusted artifact packages:

```powershell
python -m pip install -e "ml\anomaly_detection"
python -m pip install -e "ml\incident_classification"
python -m pip install -e "ml\model_lifecycle[test]"
```

The default backend is `.runtime/mlflow/mlflow.db`; logged artifacts live in
`.runtime/mlflow/artifacts`. Both are ignored. See
`docs/model-lifecycle.md` for the lifecycle and commands.
