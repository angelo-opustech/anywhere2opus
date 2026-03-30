from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import QueuePool
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.app_debug,
)


@event.listens_for(engine, "connect")
def connect(dbapi_connection, connection_record):
    logger.debug("Database connection established")


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a SQLAlchemy database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables() -> None:
    """Create all tables that don't yet exist.

    Used as a lightweight dev/test helper and as a safety net on startup.
    Schema evolution in production is handled by Alembic migrations
    (alembic/versions/). Run ``alembic upgrade head`` to apply migrations.

    For an existing production DB that was bootstrapped before Alembic was
    introduced, stamp the current revision so future migrations apply cleanly:

        alembic stamp 0001_initial_schema
    """
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """Drop all tables. Use with extreme caution — irreversible."""
    Base.metadata.drop_all(bind=engine)
