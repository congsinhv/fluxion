"""create seed tenant data procedure

Revision ID: 2bc76b6f39ea
Revises: 7400fe8d7a01
Create Date: 2026-04-03 15:13:57.647557

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bc76b6f39ea'
down_revision: Union[str, None] = '7400fe8d7a01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION seed_tenant_data(schema_name TEXT) RETURNS VOID AS $$
    BEGIN
        -- Services
        EXECUTE format('
            INSERT INTO %I.services (id, name, is_enabled) VALUES
                (1, ''Inventory'', TRUE),
                (2, ''Supply Chain'', FALSE),
                (3, ''Postpaid'', TRUE)
        ', schema_name);

        -- States
        EXECUTE format('
            INSERT INTO %I.states (id, name) VALUES
                (1, ''Idle''),
                (2, ''Registered''),
                (3, ''Enrolled''),
                (4, ''Active''),
                (5, ''Locked''),
                (6, ''Released'')
        ', schema_name);

        -- Policies (each policy -> 1 state)
        EXECUTE format('
            INSERT INTO %I.policies (id, name, state_id, service_type_id) VALUES
                (1, ''Idle'', 1, 1),
                (2, ''Registered'', 2, 3),
                (3, ''Enrolled'', 3, 3),
                (4, ''Active'', 4, 3),
                (5, ''Locked'', 5, 3),
                (6, ''Released'', 6, 3)
        ', schema_name);

        -- Actions (transitions: from_state_id -> apply_policy_id)
        EXECUTE format('
            INSERT INTO %I.actions (name, action_type_id, from_state_id, apply_policy_id, service_type_id) VALUES
                (''Upload'', 1, NULL, 1, NULL),
                (''Register'', 2, 1, 2, 1),
                (''Checkin'', 3, 2, 3, 3),
                (''Activate'', 4, 3, 4, 3),
                (''Lock'', 5, 4, 5, 3),
                (''Unlock'', 6, 5, 4, 3),
                (''Send Message'', 7, 4, 4, 3),
                (''Lock Message'', 8, 5, 5, 3),
                (''Release'', 9, 4, 6, 3),
                (''Release'', 9, 5, 6, 3),
                (''Deregister'', 10, 4, 1, 3),
                (''Deregister'', 10, 5, 1, 3)
        ', schema_name);
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS seed_tenant_data(TEXT);")
