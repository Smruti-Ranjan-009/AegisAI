# AegisAI incident classification

Phase 6 builds one supervised example per validated fault run after applying the
frozen Phase 5 anomaly model. It has no service API and does not classify normal
telemetry.

```powershell
python -m pip install -e "ml\anomaly_detection[test]"
python -m pip install -e "ml\incident_classification[test]"

python -m aegis_classifier.cli build --feature-dataset <phase4-dataset-id>
python -m aegis_classifier.cli readiness --dataset <classification-dataset-id>
python -m aegis_classifier.cli train --dataset <classification-dataset-id>
python -m aegis_classifier.cli evaluate --model <classifier-model-id>
python -m aegis_classifier.cli score --model <classifier-model-id> --dataset <classification-dataset-id>
```

Joblib uses pickle internally. Load only trusted, locally generated Phase 5 and
Phase 6 artifacts.
