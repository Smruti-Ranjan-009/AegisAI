from __future__ import annotations

from pathlib import Path

import pytest

from aegis_lifecycle.config import LifecycleConfig, sqlite_uri
from aegis_lifecycle.errors import LifecycleError
from aegis_lifecycle.integrity import sha256_file, verify_hash
from aegis_lifecycle.lineage import reject_large_or_raw
from aegis_lifecycle.tracking import safe_tags


def test_default_paths_are_repo_local(tmp_path: Path) -> None:
    config = LifecycleConfig.from_environment(tmp_path)
    assert config.runtime_root == (tmp_path / ".runtime" / "mlflow").resolve()
    assert config.database_path.name == "mlflow.db"
    assert config.artifact_root == (config.runtime_root / "artifacts").resolve()
    assert config.tracking_uri == sqlite_uri(config.database_path)


def test_environment_overrides_are_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "alternate runtime"
    artifacts = tmp_path / "artifact store"
    monkeypatch.setenv("AEGIS_MLFLOW_RUNTIME_ROOT", str(runtime))
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", str(artifacts))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:///custom.db")
    config = LifecycleConfig.from_environment(tmp_path / "repo")
    assert config.runtime_root == runtime.resolve()
    assert config.artifact_root == artifacts.resolve()
    assert config.tracking_uri == "sqlite:///custom.db"


def test_blank_optional_overrides_keep_repo_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AEGIS_MLFLOW_RUNTIME_ROOT", "")
    monkeypatch.setenv("AEGIS_MLFLOW_DATABASE_PATH", "")
    monkeypatch.setenv("MLFLOW_ARTIFACT_ROOT", "")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")
    config = LifecycleConfig.from_environment(tmp_path)
    assert config.runtime_root == (tmp_path / ".runtime" / "mlflow").resolve()
    assert config.artifact_root == (config.runtime_root / "artifacts").resolve()
    assert config.tracking_uri == sqlite_uri(config.database_path)


def test_ensure_directories(lifecycle_config: LifecycleConfig) -> None:
    lifecycle_config.ensure_directories()
    assert lifecycle_config.runtime_root.is_dir()
    assert lifecycle_config.artifact_root.is_dir()


def test_sha256_changes_and_missing_fails(tmp_path: Path) -> None:
    target = tmp_path / "artifact.bin"
    target.write_bytes(b"one")
    first = sha256_file(target)
    assert sha256_file(target) == first
    target.write_bytes(b"two")
    assert sha256_file(target) != first
    with pytest.raises(LifecycleError, match="artifact_missing"):
        sha256_file(tmp_path / "missing")


def test_hash_verification_detects_mutation(tmp_path: Path) -> None:
    target = tmp_path / "model.joblib"
    target.write_bytes(b"trusted")
    expected = sha256_file(target)
    target.write_bytes(b"changed")
    with pytest.raises(LifecycleError, match="artifact_integrity_mismatch"):
        verify_hash(target, expected)


@pytest.mark.parametrize("key", ["password", "api_token", "aws_access_key", "client_secret"])
def test_sensitive_keys_are_rejected(key: str) -> None:
    with pytest.raises(LifecycleError, match="sensitive_parameter"):
        safe_tags({key: "must-not-log"})


def test_raw_and_parquet_artifacts_are_blocked(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    raw = repository / "data" / "raw" / "run" / "metrics.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_text("{}", encoding="utf-8")
    with pytest.raises(LifecycleError, match="artifact_not_allowed"):
        reject_large_or_raw(raw, repository)
