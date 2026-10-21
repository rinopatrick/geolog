"""Alembic environment for GeoLog.

The database URL comes from backend.database so the app and the migrations can
never disagree about which file they are operating on (GEOLOG_DB_PATH, or the
app default).

`render_as_batch=True` is required for SQLite: without it, autogenerate cannot
emit ALTER COLUMN / drop-constraint operations, because SQLite has no ALTER
COLUMN and the workaround is table rebuild.
"""

from __future__ import annotations

import pathlib
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.database import Base, SQLALCHEMY_DATABASE_URL  # noqa: E402

_IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite")
from backend import models  # noqa: E402,F401  (import registers the tables)

config = context.config
config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):
    """Keep Alembic out of tables it does not own.

    `alembic_version` is Alembic's own bookkeeping, and SQLite's internal
    `sqlite_*` tables are not part of the application schema.
    """
    if type_ == "table" and name in {"alembic_version"}:
        return False
    if type_ == "table" and name.startswith("sqlite_"):
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade --sql)."""
    context.configure(
        url=SQLALCHEMY_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_IS_SQLITE,
        include_object=_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_IS_SQLITE,
            include_object=_include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
