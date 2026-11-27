from app.core.config import Settings


def test_database_url_normalizes_to_psycopg() -> None:
    s1 = Settings(DATABASE_URL="postgresql://user:pass@host/db?sslmode=require")
    assert s1.DATABASE_URL == "postgresql+psycopg://user:pass@host/db?sslmode=require"

    s2 = Settings(DATABASE_URL="postgres://user:pass@host/db")
    assert s2.DATABASE_URL == "postgresql+psycopg://user:pass@host/db"

    s3 = Settings(DATABASE_URL="postgresql+psycopg://user:pass@host/db")
    assert s3.DATABASE_URL == "postgresql+psycopg://user:pass@host/db"
