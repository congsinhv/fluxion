"""Seed action/upload permission catalog — 3 new resolver permission codes.

Revision ID: cc44f3b5a815
Revises: b9c3d1e2f4a5
Create Date: 2026-04-26

Inserts the 3 permission codes consumed by action_resolver and upload_resolver
into ``accesscontrol.permissions``. Idempotent via ``ON CONFLICT (code) DO NOTHING``:
safe to re-run, and safe if a manual insert already exists.

Permission codes (GH-35 — action_resolver + upload_resolver):
  action:execute  — assignAction / assignBulkAction (Command Pipeline write entry)
  actionlog:read  — getActionLog / listActionLogs / generateActionLogErrorReport
  upload:write    — uploadDevices bulk intake
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "cc44f3b5a815"
down_revision = "b9c3d1e2f4a5"
branch_labels = None
depends_on = None

_PERMISSIONS: list[tuple[str, str]] = [
    ("action:execute", "assignAction / assignBulkAction — Command Pipeline write entry"),
    ("actionlog:read", "getActionLog / listActionLogs / generateActionLogErrorReport"),
    ("upload:write", "uploadDevices bulk device intake"),
]


def upgrade() -> None:
    """Insert 3 permission codes; skip silently if already present."""
    for code, description in _PERMISSIONS:
        op.execute(
            sa.text(
                """
                INSERT INTO accesscontrol.permissions (code, description)
                VALUES (:code, :description)
                ON CONFLICT (code) DO NOTHING
                """
            ).bindparams(code=code, description=description)
        )


def downgrade() -> None:
    """Remove the 3 seeded permission codes (and their grants via CASCADE)."""
    codes = [code for code, _ in _PERMISSIONS]
    op.execute(
        sa.text("DELETE FROM accesscontrol.permissions WHERE code = ANY(:codes)").bindparams(
            codes=codes
        )
    )
