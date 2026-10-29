"""Database setup with SQLite default and opt-in PostgreSQL.

`GEOLOG_DATABASE_URL` wins over `GEOLOG_DB_PATH`. PostgreSQL URLs use the
`postgresql+psycopg://` driver. File-backed state (snapshots, metrics, jobs,
locks) intentionally remains on disk in both modes.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

_backend_dir = os.path.dirname(os.path.abspath(__file__))
_db_path = os.environ.get("GEOLOG_DB_PATH") or os.path.join(_backend_dir, "geolog.db")

if os.environ.get("GEOLOG_DATABASE_URL"):
    SQLALCHEMY_DATABASE_URL = os.environ["GEOLOG_DATABASE_URL"].strip()
else:
    _db_parent = os.path.dirname(os.path.abspath(_db_path))
    if _db_parent:
        os.makedirs(_db_parent, exist_ok=True)
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{_db_path}"

DATABASE_DIALECT = "postgresql" if SQLALCHEMY_DATABASE_URL.startswith("postgresql") else "sqlite"

if DATABASE_DIALECT == "sqlite":
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 15},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):
        # WAL lets readers proceed while a writer holds the database, and the
        # busy timeout makes concurrent writers wait instead of failing at once.
        # Both are per-connection settings on SQLite.
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=int(os.environ.get("GEOLOG_DB_POOL_SIZE", "5") or 5),
        max_overflow=int(os.environ.get("GEOLOG_DB_MAX_OVERFLOW", "10") or 10),
        echo=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
