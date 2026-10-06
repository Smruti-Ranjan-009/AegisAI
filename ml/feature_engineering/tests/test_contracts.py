from aegis_features.contracts import feature_columns, metadata_columns, target_columns

FORBIDDEN_FEATURE_TOKENS = {
    "run_id",
    "scenario",
    "label",
    "is_anomaly",
    "feature_flag",
    "fault_configuration",
    "capture_directory",
}


def test_target_and_provenance_columns_cannot_leak_into_features() -> None:
    for dataset in ("service_windows", "metric_windows"):
        features = set(feature_columns(dataset))
        assert features.isdisjoint(FORBIDDEN_FEATURE_TOKENS)
        assert features.isdisjoint(target_columns(dataset))
        assert features.isdisjoint(metadata_columns(dataset))


def test_contract_uses_explicit_target_columns() -> None:
    assert target_columns("service_windows") == ("scenario", "label", "is_anomaly")
    assert target_columns("metric_windows") == ("scenario", "label", "is_anomaly")
