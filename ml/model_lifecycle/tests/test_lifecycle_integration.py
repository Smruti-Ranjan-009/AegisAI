from __future__ import annotations

import mlflow
import pandas as pd
import pytest
from conftest import log_fixture_version

from aegis_lifecycle.audit import read_events, registry_audit
from aegis_lifecycle.errors import LifecycleError
from aegis_lifecycle.promotion import promote, rollback
from aegis_lifecycle.registry import resolve_champion, spec_for
from aegis_lifecycle.verification import verify_alias, verify_version


@pytest.mark.integration
def test_candidate_promote_verify_and_model_uri_reload(lifecycle_client, lifecycle_config) -> None:
    version = log_fixture_version(
        lifecycle_config, lifecycle_client, "anomaly", "fixture-anomaly-v1"
    )
    spec = spec_for("anomaly")
    lifecycle_client.set_registered_model_alias(spec.registered_name, "candidate", version.version)
    result = promote(
        lifecycle_client,
        lifecycle_config,
        "anomaly",
        version.version,
        "approved fixture baseline",
    )
    assert result["status"] == "PROMOTED"
    verified = verify_alias(lifecycle_client, lifecycle_config, "anomaly", "champion")
    assert verified["status"] == "PASS"
    resolved = resolve_champion(lifecycle_client, "anomaly")
    assert resolved["version"] == str(version.version)
    prediction = mlflow.pyfunc.load_model(resolved["model_uri"]).predict(
        pd.DataFrame([[0.0]], columns=["feature"])
    )
    assert len(prediction) == 1


@pytest.mark.integration
def test_rollback_reassigns_alias_without_deleting_versions(
    lifecycle_client, lifecycle_config
) -> None:
    first = log_fixture_version(
        lifecycle_config, lifecycle_client, "anomaly", "fixture-anomaly-v1"
    )
    second = log_fixture_version(
        lifecycle_config, lifecycle_client, "anomaly", "fixture-anomaly-v2"
    )
    promote(lifecycle_client, lifecycle_config, "anomaly", first.version, "first")
    promote(lifecycle_client, lifecycle_config, "anomaly", second.version, "second")
    rollback(lifecycle_client, lifecycle_config, "anomaly", first.version, "known good")
    assert resolve_champion(lifecycle_client, "anomaly")["version"] == str(first.version)
    assert len(lifecycle_client.search_model_versions("name='AegisAI-AnomalyDetector'")) == 2
    assert [event["action"] for event in read_events(lifecycle_config)] == [
        "promote",
        "promote",
        "rollback",
    ]


@pytest.mark.integration
def test_classifier_requires_matching_approved_anomaly_champion(
    lifecycle_client, lifecycle_config
) -> None:
    classifier = log_fixture_version(
        lifecycle_config,
        lifecycle_client,
        "classifier",
        "fixture-classifier",
        upstream_anomaly_model_id="fixture-anomaly",
    )
    with pytest.raises(LifecycleError, match="upstream_dependency_missing"):
        verify_version(lifecycle_client, lifecycle_config, "classifier", classifier.version)
    anomaly = log_fixture_version(
        lifecycle_config, lifecycle_client, "anomaly", "other-anomaly"
    )
    promote(lifecycle_client, lifecycle_config, "anomaly", anomaly.version, "wrong upstream")
    with pytest.raises(LifecycleError, match="upstream_dependency_missing"):
        verify_version(lifecycle_client, lifecycle_config, "classifier", classifier.version)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("approved", "schema", "missing_metric", "match"),
    [
        (False, "1", None, "not lifecycle-approved"),
        (True, "2", None, "Only feature schema"),
        (True, "1", "test_f1", "Required finite metric"),
    ],
)
def test_invalid_anomaly_versions_fail_promotion(
    lifecycle_client,
    lifecycle_config,
    approved: bool,
    schema: str,
    missing_metric: str | None,
    match: str,
) -> None:
    version = log_fixture_version(
        lifecycle_config,
        lifecycle_client,
        "anomaly",
        f"invalid-{approved}-{schema}-{missing_metric}",
        approved=approved,
        schema_version=schema,
        missing_metric=missing_metric,
    )
    with pytest.raises(LifecycleError, match=match):
        promote(lifecycle_client, lifecycle_config, "anomaly", version.version)


@pytest.mark.integration
def test_audit_is_compact(lifecycle_client, lifecycle_config) -> None:
    version = log_fixture_version(
        lifecycle_config, lifecycle_client, "anomaly", "fixture-audit"
    )
    promote(lifecycle_client, lifecycle_config, "anomaly", version.version, "audit")
    result = registry_audit(lifecycle_client, lifecycle_config)
    row = result["models"][0]
    assert row["source_model_id"] == "fixture-audit"
    assert row["champion"] is True
    assert "manifest" not in row
