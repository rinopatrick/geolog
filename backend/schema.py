"""Schema management.

Before this, the app called ``Base.metadata.create_all()`` at import and then ran
five ad-hoc ``_ensure_*`` helpers that issued raw ALTER/CREATE statements inside
``try/except: pass``.

That combination is worse than it looks. ``create_all()`` creates missing
*tables*, never missing *columns*, so adding a field to a model reached a fresh
database (which gets the full schema) but silently not an existing one — the
first query touching it then failed with "no such column". The helpers were the
manual workaround, and because they swallowed every exception they could not tell
you when they had not done their job.

Alembic now owns the schema. Three things happen at startup:

1. ``run_migrations()`` brings the database to head.
2. ``verify_schema()`` compares the live database against the models and reports
   any table or column that is missing or unexpected. This is the check that
   would have caught the silent-drift case above.
3. ``check_for_pending_migrations()`` reports model changes that have no
   migration, so drift is visible at boot rather than at first query.
"""

from __future__ import annotations

import logging
import os
import pathlib
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

try:
    from database import Base, engine
except ImportError:
    from backend.database import Base, engine

logger = logging.getLogger("geolog")

DEV_ENVIRONMENTS = {"dev", "local", "test", "ci"}


def _env_truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _current_env() -> str:
    return (os.getenv("GEOLOG_ENV") or os.getenv("ENV") or "dev").strip().lower()


def run_migrations_on_startup() -> bool:
    """Dev/test convenience only. Production migrates as a deploy step."""
    return _env_truthy("GEOLOG_RUN_MIGRATIONS_ON_STARTUP", _current_env() in DEV_ENVIRONMENTS)


def fail_on_schema_mismatch() -> bool:
    return _env_truthy("GEOLOG_FAIL_ON_SCHEMA_MISMATCH", _current_env() not in DEV_ENVIRONMENTS)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "migrations"))
    # env.py resolves the URL itself, so nothing to set here.
    return cfg


def run_migrations() -> None:
    """Bring the database up to head.

    A database created before Alembic existed already has the baseline schema —
    the old ``_ensure_*`` helpers kept it current on every start — but has no
    ``alembic_version`` row. Stamping it at head records that fact instead of
    replaying the baseline and failing on the first CREATE TABLE.
    """
    cfg = _alembic_config()
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())

    if existing and "alembic_version" not in existing:
        logger.info(
            "Existing pre-Alembic database detected; stamping baseline %s",
            _head_revision(cfg),
        )
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")


def _head_revision(cfg: Config) -> Optional[str]:
    try:
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        return None


def current_revision() -> Optional[str]:
    """Revision the database is currently at, or None if unversioned."""
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def verify_schema() -> list[str]:
    """Compare the live database against the models.

    Returns a list of human-readable problems; empty means the two agree. Only
    application tables are considered — ``alembic_version`` and SQLite internals
    are not part of the model.
    """
    problems: list[str] = []
    inspector = inspect(engine)
    live_tables = {
        t for t in inspector.get_table_names()
        if t != "alembic_version" and not t.startswith("sqlite_")
    }
    model_tables = set(Base.metadata.tables)

    for missing in sorted(model_tables - live_tables):
        problems.append(f"table '{missing}' is defined in the models but missing from the database")

    for table in sorted(model_tables & live_tables):
        live_columns = {c["name"] for c in inspector.get_columns(table)}
        model_columns = {c.name for c in Base.metadata.tables[table].columns}
        for missing in sorted(model_columns - live_columns):
            problems.append(
                f"column '{table}.{missing}' is defined in the models but missing from the database"
            )

    return problems


def check_for_pending_migrations() -> list[str]:
    """Report model changes that no migration accounts for.

    This is the same comparison ``alembic check`` performs. It is reported rather
    than raised so that a developer who has just edited a model still gets a
    running app, with a loud warning instead of a silent schema mismatch.
    """
    try:
        from alembic.autogenerate import compare_metadata

        with engine.connect() as conn:
            context = MigrationContext.configure(
                conn,
                opts={"compare_type": True, "include_object": lambda o, n, t, r, c: not (
                    t == "table" and (n == "alembic_version" or n.startswith("sqlite_"))
                )},
            )
            diff = compare_metadata(context, Base.metadata)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not check for pending migrations: %s", exc)
        return []

    problems: list[str] = []
    for entry in diff:
        kind = entry[0] if isinstance(entry, tuple) and entry else "change"
        detail = entry[1] if isinstance(entry, tuple) and len(entry) > 1 else entry
        problems.append(f"{kind}: {detail}")
    return problems


def ensure_schema(verify: bool = True) -> None:
    """Migrate, then optionally verify. Used by tests and one-off commands."""
    run_migrations()

    if not verify:
        return

    problems = verify_schema()
    if problems:
        for problem in problems:
            logger.error("Schema mismatch: %s", problem)
        logger.error(
            "Database schema does not match the models (%d problem(s)). "
            "Run: alembic upgrade head",
            len(problems),
        )
    else:
        logger.info("Schema verified at revision %s", current_revision())


def bootstrap_schema() -> None:
    """Startup policy: migrate in dev/test, verify (and fail) in production.

    Running Alembic from every worker/replica races on the same DDL. Production
    deploys must run `alembic upgrade head` once, then start the app with this
    function only verifying that the live schema matches the models.
    """
    if run_migrations_on_startup():
        run_migrations()
    else:
        logger.info(
            "Startup migrations disabled (GEOLOG_ENV=%s); expecting a deploy-step migration",
            _current_env(),
        )

    problems = verify_schema()
    if problems:
        for problem in problems:
            logger.error("Schema mismatch: %s", problem)
        message = (
            f"Database schema does not match the models ({len(problems)} problem(s)); "
            "run: alembic upgrade head"
        )
        if fail_on_schema_mismatch():
            raise RuntimeError(message)
        logger.error(message)
    else:
        logger.info("Schema verified at revision %s", current_revision())

    pending = check_for_pending_migrations()
    if pending:
        logger.warning(
            "Model changes have no migration (%d); run alembic revision --autogenerate: %s",
            len(pending),
            pending[:5],
        )
