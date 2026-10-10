from pathlib import Path

from aegis_rag_generation.provider import FakeSLMProvider
from helpers import artifact, generator, grounded_payload

from aegis_rag_evaluation.adversarial import adversarial_result, apply_overlay
from aegis_rag_evaluation.benchmark import load_benchmark
from aegis_rag_evaluation.config import EvaluationConfig
from aegis_rag_evaluation.runner import _generate_case
from aegis_rag_evaluation.scoring import _score_case

ROOT = Path(__file__).resolve().parents[3]


def test_sentinel_leak_is_detected() -> None:
    bundle = load_benchmark(EvaluationConfig.from_environment(ROOT))
    overlay = bundle.overlays["e2e-a-036"]
    value = artifact()
    value["structured_response"]["summary"] = overlay.sentinel
    result = adversarial_result(
        value, overlay, expected_status="grounded", claims_supported=True
    )
    assert not result["passed"]
    assert "sentinel_disclosure" in result["failure_reasons"]


def test_overlay_is_applied_after_retrieval_and_gold_never_enters_prompt(tmp_path: Path) -> None:
    config = EvaluationConfig.from_environment(ROOT)
    bundle = load_benchmark(config)
    case = next(case for case in bundle.cases if case.case_id == "e2e-a-036")
    provider = FakeSLMProvider(grounded_payload())
    result = _generate_case(case, "canonical", bundle, generator(tmp_path, provider))
    prompt = provider.last_user_prompt
    assert result["error"] is None
    assert "<EVALUATION_ONLY_UNTRUSTED_OVERLAY>" in prompt
    assert "<EVIDENCE_RECORD>" in prompt
    gold = bundle.gold[case.case_id]
    assert all(fact not in prompt for fact in gold.required_facts)
    assert all(action not in prompt for action in gold.acceptable_actions)
    assert "expected_status" not in prompt
    assert "relevance grade" not in prompt


def test_overlay_helper_preserves_original_content() -> None:
    bundle = load_benchmark(EvaluationConfig.from_environment(ROOT))
    result = apply_overlay("ORIGINAL", bundle.overlays["e2e-a-036"])
    assert result.startswith("ORIGINAL")
    assert result.count("AEGIS_FAKE_SECRET_DO_NOT_OUTPUT") == 1


def test_adversarial_schema_failure_counts_as_failed_attack() -> None:
    bundle = load_benchmark(EvaluationConfig.from_environment(ROOT))
    case = next(case for case in bundle.cases if case.case_id == "e2e-a-036")
    generated = {
        "error": {"type": "GenerationValidationError", "message": "invalid"},
        "structured_response": None,
        "retrieved_results": [],
        "reranked_results": [],
        "generation_timing": {},
    }
    row = _score_case(
        generated,
        case,
        bundle.gold[case.case_id],
        bundle,
        None,
        None,
    )
    assert row["adversarial"]["passed"] is False
    assert "schema_failure" in row["failure_categories"]
    assert "prompt_injection_failure" in row["failure_categories"]
