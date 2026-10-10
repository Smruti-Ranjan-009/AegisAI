from __future__ import annotations

from collections.abc import Iterable


def section_key(value: dict[str, object]) -> tuple[str, tuple[str, ...]]:
    return str(value["source_path"]), tuple(str(item) for item in value["heading_path"])


def structured_answer_text(response: dict[str, object]) -> str:
    parts = [str(response.get("summary", ""))]
    fields = (
        ("Suspected cause", "suspected_causes"),
        ("Recommended action", "recommended_actions"),
    )
    for name, field in fields:
        for item in response.get(field, []):
            text_key = "cause" if field == "suspected_causes" else "action"
            parts.append(f"{name}: {item[text_key]}")
    return "\n".join(part for part in parts if part.strip())


def ordered_evidence_text(
    evidence_ids: Iterable[str], evidence: list[dict[str, object]]
) -> str:
    by_id = {str(item["evidence_id"]): str(item["content"]) for item in evidence}
    return "\n\n".join(by_id[item] for item in evidence_ids if item in by_id)
