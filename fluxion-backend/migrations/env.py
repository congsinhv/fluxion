"""Alembic environment — reads DATABASE_URI from environment.

Multi-tenant aware. Migrations are raw-SQL (no SQLAlchemy ORM), so
`target_metadata = None` stays. Helper `iter_active_tenant_schemas` exposes
the `accesscontrol.tenants` registry to future ALTER migrations that need
to loop DDL across every tenant schema.

See docs/design-patterns.md §11 (tenant-per-schema) and
docs/code-standards.md §5.2 (migration style).
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.exc import ProgrammingError

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

# ---------------------------------------------------------------------------
# Alembic Config — gives access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Inject DATABASE_URI from environment so it is never hardcoded in config.
# Fail fast at migration time if the var is missing.
database_uri: str = os.environ["DATABASE_URI"]
config.set_main_option("sqlalchemy.url", database_uri)

# Set up Python logging from alembic.ini [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata: raw-SQL migrations only — autogenerate not used.
target_metadata = None


# ---------------------------------------------------------------------------
# Multi-tenant helper
# ---------------------------------------------------------------------------
def iter_active_tenant_schemas(conn: Connection) -> list[str]:
    """Return schema_name for all active rows in `accesscontrol.tenants`.

    Used by future ALTER migrations to loop DDL across every tenant schema.
    Returns [] if `accesscontrol.tenants` does not yet exist (pre-0001 state)
    so first-run migrations do not crash.
    """
    try:
        result = conn.execute(
            text(
                "SELECT schema_name FROM accesscontrol.tenants WHERE status = 'active' ORDER BY id"
            )
        )
    except ProgrammingError:
        # accesscontrol schema / tenants table not yet created
        return []
    return [row[0] for row in result.fetchall()]


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection required).

    Emits SQL to stdout rather than executing it. Useful for generating
    migration scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (direct DB connection).

    Creates a connection from the configured URL and runs all pending
    migrations inside a transaction.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
