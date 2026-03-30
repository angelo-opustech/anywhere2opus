from typing import Generator
from sqlalchemy import create_engine, event, text
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
    """Create all tables in the database. Used for initial setup or testing."""
    # Extend existing PostgreSQL enum types with new values added to the
    # Python model.  ALTER TYPE ... ADD VALUE IF NOT EXISTS is idempotent and
    # safe to run on every startup.
    _new_resource_type_values = ["KUBERNETES", "FILESTORE"]
    with engine.connect() as conn:
        for val in _new_resource_type_values:
            try:
                conn.execute(
                    text(f"ALTER TYPE resourcetype ADD VALUE IF NOT EXISTS '{val}'")
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.warning(
                    "db_enum_extend_skipped",
                    enum="resourcetype",
                    value=val,
                    reason=str(exc),
                )
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """Drop all tables. Use with extreme caution."""
    Base.metadata.drop_all(bind=engine)
