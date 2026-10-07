# AegisAI anomaly detection

Phase 5 provides reproducible offline training and scoring over Phase 4 Parquet
features. It is deliberately separate from the health-only production
`ml-service`; it does not expose an API or consume Kafka.

Install and use from the repository root:

```powershell
python -m pip install -e "ml\anomaly_detection[test]"
python -m aegis_anomaly.cli readiness --dataset <dataset-id>
python -m aegis_anomaly.cli train --dataset <dataset-id>
python -m aegis_anomaly.cli evaluate --model <model-id>
python -m aegis_anomaly.cli score --model <model-id> --dataset <dataset-id>
```

Generated model directories are written under ignored
`artifacts/anomaly_detection/`. Joblib uses Python pickle internally: only load
artifacts produced by a trusted AegisAI workflow.
