"""Grant action/upload permissions to dev admin for dev1 tenant.

Revision ID: 64066cf559b8
Revises: cc44f3b5a815
Create Date: 2026-04-26

Grants the 3 new action/upload permission codes to ``dev-admin@fluxion.local``
for the ``dev1`` tenant. The dev admin user row already exists (seeded in
b9c3d1e2f4a5); this migration only inserts ``users_permissions`` rows.

All inserts use ON CONFLICT DO NOTHING — safe to re-run.
Depends on: cc44f3b5a815 (action/upload permissions catalog).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "64066cf559b8"
down_revision = "cc44f3b5a815"
branch_labels = None
depends_on = None

_DEV_ADMIN_EMAIL = "dev-admin@fluxion.local"
_DEV1_SCHEMA = "dev1"

_PERMISSION_CODES = [
    "action:execute",
    "actionlog:read",
    "upload:write",
]


def upgrade() -> None:
    """Insert 3 permission grants for dev admin in dev1 tenant."""
    conn = op.get_bind()

    # Insert permission grants via sub-selects so we don't hard-code BIGINT IDs.
    # User row already exists from b9c3d1e2f4a5 — no user INSERT needed here.
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
    """Remove the 3 action/upload permission grants from dev admin in dev1."""
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            DELETE FROM accesscontrol.users_permissions
            WHERE user_id = (
                SELECT id FROM accesscontrol.users WHERE email = :email
            )
            AND permission_id IN (
                SELECT id FROM accesscontrol.permissions
                WHERE code = ANY(:codes)
            )
            """
        ).bindparams(email=_DEV_ADMIN_EMAIL, codes=_PERMISSION_CODES)
    )
