from aegis_rag_retrieval.tokenizer import tokenize


def test_technical_tokens_and_compounds_are_deterministic() -> None:
    text = "5xx OOM connection_pool image-provider payment p95 PostgreSQL"
    expected = [
        "5xx",
        "oom",
        "connection_pool",
        "connection",
        "pool",
        "image-provider",
        "image",
        "provider",
        "payment",
        "p95",
        "postgresql",
    ]
    assert tokenize(text) == expected
    assert tokenize(text) == tokenize(text)

