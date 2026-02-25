import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_engine(
    settings.db_url,
    # ── Connection Pool ─────────────────────────────────────────────────────
    pool_size=5,            # maxIdleConns
    max_overflow=15,        # maxOpenConns = pool_size + max_overflow = 20
    pool_recycle=3600,      # connMaxLifeTime: 1h
    pool_timeout=30,        # wait max 30s for a connection
    pool_pre_ping=True,     # auto-reconnect on stale connections
    # ── Logging ─────────────────────────────────────────────────────────────
    echo=False,             # use our own event-based logging instead
)


# ── Query logging via SQLAlchemy events ─────────────────────────────────────
@event.listens_for(engine, "before_cursor_execute")
def _log_query(conn, cursor, statement, parameters, context, executemany):
    logger.debug("[DB] %s | params=%s", statement.strip(), parameters)


@event.listens_for(engine, "connect")
def _log_connect(dbapi_conn, connection_record):
    logger.info("[DB] New connection established")


@event.listens_for(engine, "checkout")
def _log_checkout(dbapi_conn, connection_record, connection_proxy):
    logger.debug("[DB] Connection checked out from pool")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency – yields a DB session then closes it."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        logger.exception("[DB] Session error – rolling back")
        db.rollback()
        raise
    finally:
        db.close()
        logger.debug("[DB] Session closed")
