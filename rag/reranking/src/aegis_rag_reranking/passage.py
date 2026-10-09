from aegis_rag_retrieval.contracts import ChunkRecord


def passage_text(chunk: ChunkRecord) -> str:
    """Build the frozen semantic-only reranker passage representation."""
    return "\n".join(
        (
            f"Title: {chunk.title}",
            f"Heading: {' > '.join(chunk.heading_path)}",
            f"Content: {chunk.content}",
        )
    )
