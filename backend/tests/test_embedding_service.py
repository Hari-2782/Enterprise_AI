from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.services.ingestion.embedding_service import (
    EMBEDDING_DIMENSION,
    E5EmbeddingService,
)


class FakeTensor:
    def __init__(self, values):
        self.values = values

    def unsqueeze(self, _dimension):
        return self

    def __mul__(self, _other):
        return self

    def sum(self, dim):
        assert dim == 1
        return self

    def clamp(self, min):
        assert min == 1
        return self

    def __truediv__(self, _other):
        return FakeTensor([[1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
                           for _ in self.values])

    def cpu(self):
        return self

    def tolist(self):
        return self.values


class FakeTokenizer:
    def __init__(self):
        self.batches = []

    def __call__(self, texts, **kwargs):
        self.batches.append((texts, kwargs))
        return {
            "attention_mask": FakeTensor([[1, 1] for _ in texts]),
            "batch_size": len(texts),
        }


class FakeModel:
    def __call__(self, **inputs):
        return SimpleNamespace(
            last_hidden_state=FakeTensor(
                [[0.0] * EMBEDDING_DIMENSION]
                * inputs["batch_size"]
            )
        )


class FakeFunctional:
    @staticmethod
    def normalize(tensor, p, dim):
        assert p == 2
        assert dim == 1
        return tensor


class FakeTorch:
    nn = SimpleNamespace(functional=FakeFunctional())

    @staticmethod
    def inference_mode():
        return nullcontext()


def make_service(batch_size=2):
    tokenizer = FakeTokenizer()
    service = E5EmbeddingService(
        batch_size=batch_size,
        model_bundle=(FakeTorch(), tokenizer, FakeModel()),
    )
    return service, tokenizer


def test_batches_passages_and_returns_normalized_vectors():
    service, tokenizer = make_service(batch_size=2)
    vectors = service.embed_texts([
        "passage: first",
        "passage: second",
        "passage: third",
    ])

    assert [len(batch[0]) for batch in tokenizer.batches] == [2, 1]
    assert all(batch[1]["max_length"] == 512 for batch in tokenizer.batches)
    assert len(vectors) == 3
    assert all(len(vector) == EMBEDDING_DIMENSION for vector in vectors)
    assert all(vector[0] == 1.0 for vector in vectors)
    assert all(sum(value * value for value in vector) == pytest.approx(1.0)
               for vector in vectors)


def test_embed_chunks_uses_canonical_embedding_text():
    service, tokenizer = make_service()

    class Chunk:
        embedding_text = "passage: Benefits\nReceipts are required."

    service.embed_chunks([Chunk()])

    assert tokenizer.batches[0][0] == [
        "passage: Benefits\nReceipts are required."
    ]


def test_query_uses_query_prefix():
    service, tokenizer = make_service()
    service.embed_query("Where do I submit receipts?")
    assert tokenizer.batches[0][0] == [
        "query: Where do I submit receipts?"
    ]


@pytest.mark.parametrize("texts", [[""], ["ordinary unprefixed text"]])
def test_rejects_empty_or_unprefixed_passage(texts):
    service, _ = make_service()
    with pytest.raises(ValueError):
        service.embed_texts(texts)


def test_empty_batch_returns_without_loading_model():
    service = E5EmbeddingService()
    assert service.embed_texts([]) == []


def test_batch_size_must_be_positive():
    with pytest.raises(ValueError):
        E5EmbeddingService(batch_size=0)
