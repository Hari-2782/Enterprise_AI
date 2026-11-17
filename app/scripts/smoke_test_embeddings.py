import math

from app.services.ingestion.embedding_service import E5EmbeddingService


def main() -> None:
    service = E5EmbeddingService()
    vector = service.embed_texts(
        ["passage: enterprise ai embedding smoke test"]
    )[0]
    norm = math.sqrt(sum(value * value for value in vector))

    assert len(vector) == service.dimension == 384
    assert all(math.isfinite(value) for value in vector)
    assert math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4)

    print("Embedding dimensions:", len(vector))
    print("All values finite: passed")
    print("L2 norm:", norm)
    print("Real E5 embedding smoke test: passed")


if __name__ == "__main__":
    main()
