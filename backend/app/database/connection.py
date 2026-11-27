
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=1)
def get_session_factory():
    """Create the PostgreSQL engine only when a session is requested."""
    from app.core.config import settings

    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
    )
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )


def SessionLocal():
    """Return a session from the lazily initialized application pool."""
    return get_session_factory()()


def get_db():
    """Provide a database session for a request."""
    db: Session = SessionLocal()

    try:
        yield db
    finally:
        db.close()
