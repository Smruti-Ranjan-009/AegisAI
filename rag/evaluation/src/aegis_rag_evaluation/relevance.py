from __future__ import annotations

import math

from aegis_rag_evaluation.gold import structured_answer_text


def query_answer_similarity(
    query: str, response: dict[str, object], embedding_provider
) -> float | None:
    if response["status"] != "grounded":
        return None
    answer = structured_answer_text(response)
    left = embedding_provider.embed_query(query)
    right = embedding_provider.embed_query(answer)
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        raise ValueError("semantic relevance embedding has zero norm")
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator
