"""Provision dev1 — demo/dev tenant.

Revision ID: 6bbab220d60c
Revises: 4768d32c8037
Create Date: 2026-04-20

Materializes the `dev1` tenant schema at migrate time by calling the two
procedures installed in 4768d32c8037 and registering the tenant in
`accesscontrol.tenants`. Future tenants are provisioned via admin API,
not via migrations.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "6bbab220d60c"
down_revision = "4768d32c8037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create `dev1` schema + seed + register in accesscontrol.tenants."""
    op.execute("CALL public.create_tenant_schema('dev1')")
    op.execute("CALL public.create_default_tenant_data('dev1')")
    op.execute("INSERT INTO accesscontrol.tenants (schema_name, enabled) VALUES ('dev1', TRUE)")


def downgrade() -> None:
    """Remove tenants row + drop schema."""
    op.execute("DELETE FROM accesscontrol.tenants WHERE schema_name = 'dev1'")
    op.execute("DROP SCHEMA IF EXISTS dev1 CASCADE")
