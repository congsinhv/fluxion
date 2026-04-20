"""accesscontrol schema + cross-tenant identity tables.

Revision ID: 7124824094ea
Revises:
Create Date: 2026-04-20

Creates the `accesscontrol` schema holding cross-tenant identity and
authorization data: tenants registry, admin users, permissions catalog,
and user-permission grants (optionally scoped by tenant).

See docs/design-patterns.md §11 for the tenant-per-schema isolation model
and plans/260420-1348-t6-database-migration-multi-tenant/phase-02 for spec.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7124824094ea"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create accesscontrol schema + 4 tables + indexes."""
    op.execute(sa.text("CREATE SCHEMA accesscontrol"))

    op.execute(
        sa.text(
            """
            CREATE TABLE accesscontrol.tenants (
                id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                schema_name  TEXT NOT NULL,
                enabled      BOOLEAN NOT NULL DEFAULT true,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_tenants_schema_name UNIQUE (schema_name),
                CONSTRAINT ck_tenants_schema_name_format
                    CHECK (schema_name ~ '^[a-z][a-z0-9_]{0,39}$'),
                CONSTRAINT ck_tenants_schema_name_reserved
                    CHECK (schema_name NOT IN (
                        'public', 'information_schema', 'pg_catalog',
                        'pg_toast', 'accesscontrol'
                    ))
            )
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE accesscontrol.users (
                id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                email        TEXT NOT NULL,
                cognito_sub  TEXT,
                name         TEXT,
                enabled      BOOLEAN NOT NULL DEFAULT true,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_users_email UNIQUE (email),
                CONSTRAINT uq_users_cognito_sub UNIQUE (cognito_sub)
            )
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE accesscontrol.permissions (
                id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                code         TEXT NOT NULL,
                description  TEXT,
                CONSTRAINT uq_permissions_code UNIQUE (code)
            )
            """
        )
    )

    # tenant_id nullable: NULL = global grant (e.g., super-admin).
    op.execute(
        sa.text(
            """
            CREATE TABLE accesscontrol.users_permissions (
                id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                user_id        BIGINT NOT NULL
                    REFERENCES accesscontrol.users(id) ON DELETE CASCADE,
                permission_id  BIGINT NOT NULL
                    REFERENCES accesscontrol.permissions(id) ON DELETE CASCADE,
                tenant_id      BIGINT
                    REFERENCES accesscontrol.tenants(id) ON DELETE CASCADE,
                granted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_users_permissions_grant
                    UNIQUE (user_id, permission_id, tenant_id)
            )
            """
        )
    )

    op.execute(
        sa.text(
            "CREATE INDEX ix_users_permissions_user_id ON accesscontrol.users_permissions(user_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_users_permissions_tenant_id "
            "ON accesscontrol.users_permissions(tenant_id)"
        )
    )


def downgrade() -> None:
    """Drop accesscontrol schema and all contents."""
    op.execute(sa.text("DROP SCHEMA accesscontrol CASCADE"))
