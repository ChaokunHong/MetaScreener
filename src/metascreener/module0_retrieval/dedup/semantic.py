"""Layer 6: semantic deduplication using sentence-embedding cosine similarity.

If ``sentence_transformers`` is not installed the function degrades gracefully
and returns an empty list, so the engine can still run Layers 1-5.
"""
from __future__ import annotations

from typing import Any

import structlog

from metascreener.module0_retrieval.models import RawRecord

log = structlog.get_logger(__name__)

_DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


def find_semantic_duplicates(
    records: list[RawRecord],
    model: Any | None = None,
    threshold: float = 0.95,
) -> list[tuple[str, str]]:
    """Layer 6: find duplicate pairs by cosine similarity of title embeddings.

    Args:
        records: Input bibliographic records.
        model: A sentence-transformers model with an ``encode`` method.  If
            ``None``, the function attempts to load ``all-MiniLM-L6-v2``.
            When ``sentence_transformers`` is unavailable, an empty list is
            returned and a warning is logged.
        threshold: Minimum cosine similarity to consider a pair a duplicate.
            Defaults to 0.95.

    Returns:
        List of ``(anchor_id, duplicate_id)`` pairs whose title embeddings
        have cosine similarity >= *threshold*.
    """
    if len(records) < 2:
        return []

    if model is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            model = SentenceTransformer(_DEFAULT_MODEL_NAME)
        except ImportError:
            log.warning(
                "sentence_transformers not installed; skipping semantic dedup (Layer 6)"
            )
            return []

    import numpy as np

    titles = [rec.title for rec in records]
    embeddings: np.ndarray = model.encode(titles)

    # L2 normalise each embedding so dot product == cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    # Avoid division by zero for zero vectors
    norms = np.where(norms == 0, 1.0, norms)
    normed: np.ndarray = embeddings / norms

    # Pairwise cosine similarity matrix
    sim_matrix: np.ndarray = normed @ normed.T

    pairs: list[tuple[str, str]] = []
    n = len(records)
    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i, j] >= threshold:
                pairs.append((records[i].record_id, records[j].record_id))

    return pairs
