from __future__ import annotations

import pytest
from conftest import log_fixture_version

from aegis_lifecycle.errors import LifecycleError
from aegis_lifecycle.experiments import initialize_experiments
from aegis_lifecycle.integrity import sha256_file
from aegis_lifecycle.registry import find_imported_version, resolve_champion, spec_for
from aegis_lifecycle.tracking import initialize

pytestmark = pytest.mark.integration


def test_init_and_experiments_are_idempotent(lifecycle_config) -> None:
    first = initialize(lifecycle_config)
    second = initialize(lifecycle_config)
    assert first["experiments"] == second["experiments"]
    assert len(first["experiments"]) == 2


def test_experiment_names_are_stable(lifecycle_client, lifecycle_config) -> None:
    experiments = initialize_experiments(lifecycle_client, lifecycle_config)
    assert set(experiments) == {
        "aegisai-anomaly-detection",
        "aegisai-incident-classification",
    }


def test_import_lookup_reuses_identical_and_rejects_conflict(
    lifecycle_client, lifecycle_config
) -> None:
    version = log_fixture_version(
        lifecycle_config, lifecycle_client, "anomaly", "fixture-anomaly"
    )
    source = lifecycle_config.repository / version.tags["source_artifact_path"]
    found = find_imported_version(
        lifecycle_client, spec_for("anomaly"), "fixture-anomaly", sha256_file(source)
    )
    assert found.version == version.version
    source.write_bytes(b"different")
    with pytest.raises(LifecycleError, match="artifact_integrity_mismatch"):
        find_imported_version(
            lifecycle_client, spec_for("anomaly"), "fixture-anomaly", sha256_file(source)
        )


def test_champion_resolution_requires_alias(lifecycle_client) -> None:
    with pytest.raises(LifecycleError, match="alias_not_found"):
        resolve_champion(lifecycle_client, "anomaly")


def test_required_model_version_tags_are_present(lifecycle_client, lifecycle_config) -> None:
    version = log_fixture_version(
        lifecycle_config, lifecycle_client, "anomaly", "fixture-tags"
    )
    assert {
        "project",
        "phase",
        "task",
        "source_model_id",
        "source_dataset_id",
        "feature_schema_version",
        "validation_status",
        "artifact_sha256",
    } <= set(version.tags)
