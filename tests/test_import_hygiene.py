"""Import hygiene.

Several modules still use a dual import block::

    try:
        from database import Base        # top-level, when backend/ is on sys.path
    except ImportError:
        from backend.database import Base  # package style

That pattern makes the *same file* importable as two different modules, so the
two spellings produce two independent SQLAlchemy registries. Whichever one the
models bound to is not necessarily the one a caller holds, and
``Base.metadata.create_all()`` then creates nothing — silently.

Entry points must pick one convention. This guards the supported one.
"""

from __future__ import annotations


def test_models_and_database_share_one_base():
    """The package-style import must resolve to a single Base object."""
    from backend.database import Base as database_base
    from backend import models

    assert database_base is models.Base, (
        "backend.database.Base and backend.models.Base are different objects — "
        "the models were imported through the top-level 'database' module "
        "instead of 'backend.database'. Put the repo root (not backend/) on "
        "sys.path and use the backend.* spelling."
    )


def test_base_metadata_registers_the_models():
    """A Base whose metadata is empty would make create_all a no-op."""
    from backend.database import Base
    from backend import models  # noqa: F401  (import for registration side effect)

    assert len(Base.metadata.tables) > 0, (
        "Base.metadata has no tables; create_all() would silently create nothing"
    )


def test_expected_core_tables_are_registered():
    from backend.database import Base
    from backend import models  # noqa: F401

    for table in ("projects", "wells", "log_runs", "curve_data", "formation_tops",
                  "zones", "audit_log", "users"):
        assert table in Base.metadata.tables, f"{table} is not registered on Base"
