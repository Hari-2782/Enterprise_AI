import pytest

from app.services.search.evaluation import (
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_precision_recall_and_reciprocal_rank():
    retrieved = ["chunk-a", "chunk-x", "chunk-b", "chunk-c"]
    relevant = {"chunk-b", "chunk-c"}

    assert precision_at_k(retrieved, relevant, 3) == pytest.approx(1 / 3)
    assert recall_at_k(retrieved, relevant, 3) == pytest.approx(1 / 2)
    assert reciprocal_rank(retrieved, relevant) == pytest.approx(1 / 3)


def test_mean_reciprocal_rank_averages_query_ranks():
    assert mean_reciprocal_rank(
        [["a", "b"], ["x", "y", "z"], []],
        [{"b"}, {"y"}, {"missing"}],
    ) == pytest.approx((1 / 2 + 1 / 2 + 0) / 3)


@pytest.mark.parametrize("metric", [precision_at_k, recall_at_k])
def test_top_k_metrics_reject_non_positive_k(metric):
    with pytest.raises(ValueError, match="k must be positive"):
        metric(["a"], {"a"}, 0)


def test_mean_reciprocal_rank_requires_matching_query_sets():
    with pytest.raises(ValueError, match="one relevant-item set"):
        mean_reciprocal_rank([["a"]], [])
