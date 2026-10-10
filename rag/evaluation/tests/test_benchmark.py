from pathlib import Path

from aegis_rag_evaluation.benchmark import FAMILIES, STYLES, load_benchmark, manifest
from aegis_rag_evaluation.config import EvaluationConfig

ROOT = Path(__file__).resolve().parents[3]


def test_committed_benchmark_contract_and_section_resolution() -> None:
    config = EvaluationConfig.from_environment(ROOT)
    bundle = load_benchmark(config)
    value = manifest(bundle, config)
    assert value["counts"] == {"grounded": 30, "insufficient": 5, "adversarial": 5}
    assert value["splits"] == {"development": 25, "final": 15}
    assert bundle.benchmark_id.startswith("e2e-rag-v1-")


def test_final_grounded_is_balanced() -> None:
    bundle = load_benchmark(EvaluationConfig.from_environment(ROOT))
    cases = [
        case
        for case in bundle.cases
        if case.split == "final" and case.case_type == "grounded"
    ]
    assert {name: sum(case.incident_family == name for case in cases) for name in FAMILIES} == {
        name: 2 for name in FAMILIES
    }
    assert {name: sum(case.query_style == name for case in cases) for name in STYLES} == {
        name: 2 for name in STYLES
    }


def test_adversarial_overlays_are_evaluation_only() -> None:
    bundle = load_benchmark(EvaluationConfig.from_environment(ROOT))
    assert len(bundle.overlays) == 5
    assert all(overlay.evaluation_only for overlay in bundle.overlays.values())
    corpus = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "rag" / "knowledge").rglob("*.md")
    )
    assert "AEGIS_FAKE_SECRET_DO_NOT_OUTPUT" not in corpus
