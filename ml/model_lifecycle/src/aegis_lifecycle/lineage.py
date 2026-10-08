from __future__ import annotations

from pathlib import Path

from .errors import LifecycleError


def _required(directory: Path, names: tuple[str, ...]) -> dict[str, Path]:
    paths = {name: directory / name for name in names}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise LifecycleError(
            "artifact_missing", f"Required lineage files are missing: {', '.join(missing)}"
        )
    return paths


def anomaly_lineage(repository: Path, model_id: str, dataset_id: str) -> dict[str, Path]:
    model_dir = repository / "artifacts" / "anomaly_detection" / model_id
    dataset_dir = repository / "data" / "features" / dataset_id
    values = {
        **{f"source/{name}": path for name, path in _required(
            model_dir,
            (
                "manifest.json",
                "metrics.json",
                "feature_schema.json",
                "split.json",
                "threshold.json",
            ),
        ).items()},
        **{f"datasets/feature/{name}": path for name, path in _required(
            dataset_dir, ("manifest.json", "quality.json")
        ).items()},
    }
    catalog = repository / "ml" / "feature_engineering" / "feature_catalog_v1.json"
    if not catalog.is_file():
        raise LifecycleError("artifact_missing", f"Feature catalog missing: {catalog}")
    values["datasets/feature/feature_catalog_v1.json"] = catalog
    return values


def classifier_lineage(
    repository: Path,
    model_id: str,
    feature_dataset_id: str,
    classification_dataset_id: str,
) -> dict[str, Path]:
    model_dir = repository / "artifacts" / "incident_classification" / model_id
    feature_dir = repository / "data" / "features" / feature_dataset_id
    classification_dir = repository / "data" / "classification" / classification_dataset_id
    values = {
        **{f"source/{name}": path for name, path in _required(
            model_dir,
            (
                "manifest.json",
                "metrics.json",
                "feature_schema.json",
                "split.json",
                "cv_results.json",
            ),
        ).items()},
        **{f"datasets/feature/{name}": path for name, path in _required(
            feature_dir, ("manifest.json", "quality.json")
        ).items()},
        **{f"datasets/classification/{name}": path for name, path in _required(
            classification_dir, ("manifest.json", "quality.json", "split.json")
        ).items()},
    }
    catalog = repository / "ml" / "incident_classification" / "feature_catalog_v1.json"
    if not catalog.is_file():
        raise LifecycleError("artifact_missing", f"Classification catalog missing: {catalog}")
    values["datasets/classification/feature_catalog_v1.json"] = catalog
    return values


def reject_large_or_raw(path: Path, repository: Path) -> None:
    relative = path.resolve().relative_to(repository.resolve()).as_posix()
    if relative.startswith("data/raw/") or path.suffix.lower() in {".parquet", ".jsonl"}:
        raise LifecycleError(
            "artifact_not_allowed", f"Large/raw lineage logging is blocked: {path}"
        )


def relative_to_repository(path: Path, repository: Path) -> str:
    try:
        return path.resolve().relative_to(repository.resolve()).as_posix()
    except ValueError as exc:
        raise LifecycleError(
            "artifact_integrity_mismatch", f"Artifact is outside the repository: {path}"
        ) from exc
