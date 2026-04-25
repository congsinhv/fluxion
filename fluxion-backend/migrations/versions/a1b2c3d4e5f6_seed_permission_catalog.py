"""Seed permission catalog — 6 resolver permission codes.

Revision ID: a1b2c3d4e5f6
Revises: 6bbab220d60c
Create Date: 2026-04-22

Inserts the 6 permission codes consumed by device/platform/user resolvers
into ``accesscontrol.permissions``. Idempotent via ``ON CONFLICT (code) DO NOTHING``:
safe to re-run, and safe if a manual insert already exists.

Permission codes (design-patterns.md §11 + GH-34 brainstorm):
  device:read     — list/get devices in a tenant
  platform:read   — list/get MDM platform configs
  platform:admin  — create/update/delete platform configs
  user:self       — read/update own user profile
  user:read       — list/get other users in a tenant
  user:admin      — create/update/delete users

NOTE: No ``accesscontrol.users`` seed is inserted here.
      Dev tenant admin user is seeded in P5 (GH-34). The absence of a user
      row means P2 smoke tests that exercise permission checks must use a
      pre-seeded Cognito sub or mock the DB layer.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "6bbab220d60c"
branch_labels = None
depends_on = None

_PERMISSIONS: list[tuple[str, str]] = [
    ("device:read", "List and retrieve devices within a tenant"),
    ("platform:read", "List and retrieve MDM platform configurations"),
    ("platform:admin", "Create, update and delete MDM platform configurations"),
    ("user:self", "Read and update own user profile"),
    ("user:read", "List and retrieve other users within a tenant"),
    ("user:admin", "Create, update and delete users within a tenant"),
]


def upgrade() -> None:
    """Insert 6 permission codes; skip silently if already present."""
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
    """Remove the 6 seeded permission codes (and their grants via CASCADE)."""
    codes = [code for code, _ in _PERMISSIONS]
    op.execute(
        sa.text("DELETE FROM accesscontrol.permissions WHERE code = ANY(:codes)").bindparams(
            codes=codes
        )
    )
