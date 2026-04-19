"""Alembic environment — reads DATABASE_URI from environment.

Standard Alembic env.py skeleton. Real migration logic (multi-tenant schema
iteration) will be added in ticket #31. For now this supports single-schema
online migrations used during development.

See docs/code-standards.md §5.2 for migration style rules.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

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

# target_metadata: set to your SQLAlchemy MetaData object to enable
# autogenerate support. Left as None until models are defined in #31.
target_metadata = None


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
