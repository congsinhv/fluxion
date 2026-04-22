"""Seed dev admin user + tenant-scoped permission grants.

Revision ID: b9c3d1e2f4a5
Revises: a1b2c3d4e5f6
Create Date: 2026-04-22

Seeds the cross-tenant dev admin user and all 6 permission grants against the
``dev1`` tenant. Designed for GH-34 E2E smoke (P5).

Design decisions:
- Inserts user row with cognito_sub=NULL; provision-dev-admin.sh fills it later.
- Grants are scoped to the dev1 tenant (tenant_id = dev1's BIGINT id).
- All inserts use ON CONFLICT DO NOTHING — safe to re-run.
- Depends on: a1b2c3d4e5f6 (permissions catalog) + 6bbab220d60c (dev1 tenant).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b9c3d1e2f4a5"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

_DEV_ADMIN_EMAIL = "dev-admin@fluxion.local"
_DEV_ADMIN_NAME = "Dev Admin"
_DEV1_SCHEMA = "dev1"

_PERMISSION_CODES = [
    "device:read",
    "platform:read",
    "platform:admin",
    "user:self",
    "user:read",
    "user:admin",
]


def upgrade() -> None:
    """Insert dev admin user row + 6 permission grants for dev1 tenant."""
    conn = op.get_bind()

    # 1. Ensure user row exists (cognito_sub populated later by provision script).
    conn.execute(
        sa.text(
            """
            INSERT INTO accesscontrol.users (email, name, enabled)
            VALUES (:email, :name, TRUE)
            ON CONFLICT (email) DO NOTHING
            """
        ).bindparams(email=_DEV_ADMIN_EMAIL, name=_DEV_ADMIN_NAME)
    )

    # 2. Insert permission grants via sub-selects so we don't hard-code BIGINT IDs.
    for code in _PERMISSION_CODES:
        conn.execute(
            sa.text(
                """
                INSERT INTO accesscontrol.users_permissions (user_id, permission_id, tenant_id)
                SELECT u.id, p.id, t.id
                FROM   accesscontrol.users       u,
                       accesscontrol.permissions p,
                       accesscontrol.tenants     t
                WHERE  u.email       = :email
                  AND  p.code        = :code
                  AND  t.schema_name = :schema_name
                ON CONFLICT (user_id, permission_id, tenant_id) DO NOTHING
                """
            ).bindparams(
                email=_DEV_ADMIN_EMAIL,
                code=code,
                schema_name=_DEV1_SCHEMA,
            )
        )


def downgrade() -> None:
    """Remove permission grants + user row inserted by this migration."""
    conn = op.get_bind()

    # Remove grants first (FK → user); then remove user row.
    conn.execute(
        sa.text(
            """
            DELETE FROM accesscontrol.users_permissions
            WHERE user_id = (
                SELECT id FROM accesscontrol.users WHERE email = :email
            )
            """
        ).bindparams(email=_DEV_ADMIN_EMAIL)
    )
    conn.execute(
        sa.text(
            "DELETE FROM accesscontrol.users WHERE email = :email"
        ).bindparams(email=_DEV_ADMIN_EMAIL)
    )
