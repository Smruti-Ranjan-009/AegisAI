from helpers import chunk

from aegis_rag_retrieval.repository import corpus_fingerprint


def test_corpus_fingerprint_is_order_independent_and_content_sensitive() -> None:
    first = chunk("a", "alpha")
    second = chunk("b", "beta", document_id="doc-2", checksum="b" * 64)
    assert corpus_fingerprint((first, second)) == corpus_fingerprint((second, first))
    changed = chunk("c", "alpha")
    assert corpus_fingerprint((first, second)) != corpus_fingerprint((changed, second))
