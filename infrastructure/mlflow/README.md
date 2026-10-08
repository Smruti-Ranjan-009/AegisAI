# Local MLflow environment

Phase 7 uses an on-demand local MLflow 3.17.0 process. Metadata is stored in
the ignored SQLite database `.runtime/mlflow/mlflow.db`; MLflow artifacts are
stored below `.runtime/mlflow/artifacts`. The incident-service PostgreSQL
database and root Docker Compose stack are unrelated.

Install and initialize from the repository root:

```powershell
conda activate aegis
python -m pip install -e "ml\model_lifecycle[test]"
python -m aegis_lifecycle.cli init
```

Optional UI/server, bound only to the local machine:

```powershell
mlflow server `
  --host 127.0.0.1 `
  --port 5000 `
  --backend-store-uri sqlite:///./.runtime/mlflow/mlflow.db `
  --artifacts-destination ./.runtime/mlflow/artifacts
```

Open `http://127.0.0.1:5000`. Stop it with `Ctrl+C`; direct CLI workflows do
not need the server to remain running. Registered models are
`AegisAI-AnomalyDetector` and `AegisAI-IncidentClassifier`; use
`python -m aegis_lifecycle.cli audit` to inspect versions and aliases.

This local server has no authentication. Never bind it publicly and never log
credentials, tokens, passwords, API keys, or environment dumps. Joblib/pickle
loads are allowed only for trusted locally generated AegisAI artifacts.

To reset only local MLflow history, first stop the UI and then deliberately run:

```powershell
Remove-Item -Recurse -Force .runtime\mlflow
```

This is destructive: it removes local experiments, registry versions, aliases,
and audit history. It does not delete canonical Phase 5/6 artifacts or any raw,
feature, or classification datasets. The command is documentation only and is
never run automatically.
