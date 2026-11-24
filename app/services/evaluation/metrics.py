from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import TypeVar

from app.services.search.evaluation import (
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


T = TypeVar("T")


def ndcg_at_k(
    retrieved: Sequence[T],
    relevant: Iterable[T],
    k: int,
) -> float:
    """Compute binary Normalized Discounted Cumulative Gain at rank k."""
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0

    dcg = 0.0
    seen: set[T] = set()
    for rank, item in enumerate(retrieved[:k], start=1):
        if item in relevant_set and item not in seen:
            seen.add(item)
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def citation_correctness_score(
    cited_doc_ids: Iterable[str],
    expected_doc_ids: Iterable[str],
    *,
    should_abstain: bool,
    abstained: bool,
) -> float:
    """Measure whether citations match expected documents (or abstained appropriately)."""
    if should_abstain:
        return 1.0 if abstained else 0.0
    if abstained:
        return 0.0
    expected = set(expected_doc_ids)
    cited = set(cited_doc_ids)
    if not expected or not cited:
        return 0.0
    return len(cited & expected) / len(cited)


__all__ = [
    "citation_correctness_score",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
]
