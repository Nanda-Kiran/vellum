"""Local sentence-transformers RAG over policy documents."""

from __future__ import annotations


async def query_policy_context(question: str) -> list[dict]:
    """Return policy snippets relevant to a natural-language question."""
    _ = question
    raise NotImplementedError("TODO: Implement local policy RAG retrieval.")

