from collections.abc import Iterable, Sequence
from typing import TypeVar


T = TypeVar("T")


def precision_at_k(
    retrieved: Sequence[T],
    relevant: Iterable[T],
    k: int,
) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    hits = len(set(retrieved[:k]) & relevant_set)
    return hits / k


def recall_at_k(
    retrieved: Sequence[T],
    relevant: Iterable[T],
    k: int,
) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    hits = len(set(retrieved[:k]) & relevant_set)
    return hits / len(relevant_set)


def reciprocal_rank(
    retrieved: Sequence[T],
    relevant: Iterable[T],
) -> float:
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1 / rank
    return 0.0


def mean_reciprocal_rank(
    retrieved_by_query: Sequence[Sequence[T]],
    relevant_by_query: Sequence[Iterable[T]],
) -> float:
    if len(retrieved_by_query) != len(relevant_by_query):
        raise ValueError("Each query needs one relevant-item set")
    if not retrieved_by_query:
        return 0.0
    scores = [
        reciprocal_rank(retrieved, relevant)
        for retrieved, relevant in zip(
            retrieved_by_query,
            relevant_by_query,
            strict=True,
        )
    ]
    return sum(scores) / len(scores)
