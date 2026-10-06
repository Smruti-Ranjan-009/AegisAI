from __future__ import annotations

import json
from dataclasses import replace

import pytest

from aegis_features.config import UNKNOWN_SERVICE
from aegis_features.dataset import SourceDeduplicator
from aegis_features.errors import DataQualityError, DuplicateConflictError, InputValidationError
from aegis_features.loaders import load_manifest
from aegis_features.observations import MetricObservation
from aegis_features.quality import QualityCounters, observe, validate_observations


def _metric(**changes) -> MetricObservation:
    base = MetricObservation(
        run_id="run",
        scenario="normal",
        label="normal",
        service_name="checkout",
        timestamp_ns=1,
        source_event_id="event",
        metric_name="cpu",
        unit="1",
        metric_type="Gauge",
        series_identity="series",
        numeric_value=1.0,
    )
    return replace(base, **changes)


def test_identical_duplicate_is_counted_once() -> None:
    deduplicator = SourceDeduplicator()
    assert deduplicator.accept("event", b"payload") is True
    assert deduplicator.accept("event", b"payload") is False
    assert deduplicator.duplicates_removed == 1


def test_conflicting_duplicate_is_rejected() -> None:
    deduplicator = SourceDeduplicator()
    deduplicator.accept("event", b"first")
    with pytest.raises(DuplicateConflictError, match="conflicting payloads"):
        deduplicator.accept("event", b"second")


def test_missing_timestamp_quality_ratio_is_enforced() -> None:
    counters = QualityCounters()
    observe(counters, "metrics", [_metric(timestamp_ns=None), _metric(source_event_id="ok")])
    with pytest.raises(DataQualityError, match="timestamp ratio"):
        validate_observations(counters, 0.49)
    validate_observations(counters, 0.5)


def test_non_finite_observation_is_rejected() -> None:
    counters = QualityCounters()
    observe(counters, "metrics", [_metric(numeric_value=float("inf"))])
    with pytest.raises(DataQualityError, match="non-finite"):
        validate_observations(counters, 1.0)


def test_unknown_service_is_retained_and_counted() -> None:
    counters = QualityCounters()
    observe(counters, "metrics", [_metric(service_name=UNKNOWN_SERVICE)])
    assert counters.unknown_service_observations == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"scenario": "other"}, "Unknown scenario"),
        ({"label": "cpu_saturation"}, "matching known strings"),
        ({"validation_status": "FAIL"}, "not PASS"),
    ],
)
def test_invalid_manifest_ground_truth_is_rejected(
    tmp_path, fixture_raw_root, fixture_run_id, mutation, message
) -> None:
    target = tmp_path / fixture_run_id
    target.mkdir()
    source = fixture_raw_root / fixture_run_id
    for filename in ("metrics.jsonl", "logs.jsonl", "traces.jsonl"):
        (target / filename).write_bytes((source / filename).read_bytes())
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest.update(mutation)
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(InputValidationError, match=message):
        load_manifest(tmp_path, fixture_run_id)


def test_missing_manifest_is_rejected(tmp_path, fixture_run_id) -> None:
    (tmp_path / fixture_run_id).mkdir()
    with pytest.raises(InputValidationError, match="manifest is missing"):
        load_manifest(tmp_path, fixture_run_id)
