from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


def repository_root() -> Path:
    configured = os.getenv("AEGIS_REPOSITORY_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def sqlite_uri(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if len(resolved) >= 3 and resolved[1] == ":":
        return "sqlite:///" + quote(resolved, safe="/:")
    return "sqlite:////" + quote(resolved.lstrip("/"), safe="/")


@dataclass(frozen=True)
class LifecycleConfig:
    repository: Path
    runtime_root: Path
    database_path: Path
    artifact_root: Path
    tracking_uri: str
    audit_path: Path

    @classmethod
    def from_environment(cls, repository: Path | None = None) -> LifecycleConfig:
        repo = (repository or repository_root()).resolve()
        runtime_value = os.getenv("AEGIS_MLFLOW_RUNTIME_ROOT") or repo / ".runtime" / "mlflow"
        runtime = Path(runtime_value)
        runtime = runtime.expanduser().resolve()
        database_value = os.getenv("AEGIS_MLFLOW_DATABASE_PATH") or runtime / "mlflow.db"
        database = Path(database_value)
        database = database.expanduser().resolve()
        artifact_value = os.getenv("MLFLOW_ARTIFACT_ROOT") or runtime / "artifacts"
        artifacts = Path(artifact_value)
        artifacts = artifacts.expanduser().resolve()
        tracking = os.getenv("MLFLOW_TRACKING_URI") or sqlite_uri(database)
        return cls(
            repository=repo,
            runtime_root=runtime,
            database_path=database,
            artifact_root=artifacts,
            tracking_uri=tracking,
            audit_path=runtime / "audit.jsonl",
        )

    def ensure_directories(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
