"""create tenant tables procedure

Revision ID: 7400fe8d7a01
Revises:
Create Date: 2026-04-03 15:13:01.802260

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7400fe8d7a01'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION create_tenant_tables(schema_name TEXT) RETURNS VOID AS $$
    BEGIN
        -- Create schema
        EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', schema_name);

        -- FSM Config Tables
        EXECUTE format('
            CREATE TABLE %I.services (
                id SMALLINT PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL,
                is_enabled BOOL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name);

        EXECUTE format('
            CREATE TABLE %I.states (
                id SMALLINT PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name);

        EXECUTE format('
            CREATE TABLE %I.policies (
                id SMALLINT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                service_type_id SMALLINT REFERENCES %I.services(id),
                state_id SMALLINT REFERENCES %I.states(id),
                color VARCHAR(6),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name, schema_name, schema_name);

        EXECUTE format('
            CREATE TABLE %I.actions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL,
                action_type_id SMALLINT NOT NULL,
                from_state_id SMALLINT REFERENCES %I.states(id),
                service_type_id SMALLINT REFERENCES %I.services(id),
                apply_policy_id SMALLINT REFERENCES %I.policies(id),
                configuration JSONB,
                ext_fields JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name, schema_name, schema_name, schema_name);

        -- Core Device Tables
        EXECUTE format('
            CREATE TABLE %I.devices (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                state_id SMALLINT NOT NULL REFERENCES %I.states(id) DEFAULT 1,
                current_policy_id SMALLINT REFERENCES %I.policies(id),
                assigned_action_id UUID REFERENCES %I.actions(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name, schema_name, schema_name, schema_name);

        EXECUTE format('
            CREATE TABLE %I.device_informations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                device_id UUID NOT NULL UNIQUE REFERENCES %I.devices(id) ON DELETE CASCADE,
                serial_number VARCHAR(50) UNIQUE NOT NULL,
                udid VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(200),
                model VARCHAR(100),
                os_version VARCHAR(20),
                battery_level REAL,
                wifi_mac VARCHAR(20),
                is_supervised BOOLEAN DEFAULT FALSE,
                last_checkin_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ext_fields JSONB
            )', schema_name, schema_name);

        EXECUTE format('
            CREATE TABLE %I.device_tokens (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                device_id UUID NOT NULL UNIQUE REFERENCES %I.devices(id) ON DELETE CASCADE,
                push_token BYTEA NOT NULL,
                push_magic VARCHAR(200) NOT NULL,
                unlock_token BYTEA,
                topic VARCHAR(200) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name, schema_name);

        -- Transaction Tables
        EXECUTE format('
            CREATE TABLE %I.action_executions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                device_id UUID NOT NULL REFERENCES %I.devices(id),
                action_id UUID NOT NULL REFERENCES %I.actions(id),
                command_uuid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
                status VARCHAR(20) NOT NULL DEFAULT ''ACTION_PENDING'',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ext_fields JSONB
            )', schema_name, schema_name, schema_name);

        EXECUTE format('
            CREATE TABLE %I.milestones (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                device_id UUID NOT NULL REFERENCES %I.devices(id),
                assigned_action_id UUID REFERENCES %I.actions(id),
                policy_id SMALLINT REFERENCES %I.policies(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ext_fields JSONB
            )', schema_name, schema_name, schema_name, schema_name);

        -- User Tables
        EXECUTE format('
            CREATE TABLE %I.users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT ''operator'',
                cognito_sub VARCHAR(100) UNIQUE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name);

        -- Chat Tables
        EXECUTE format('
            CREATE TABLE %I.chat_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES %I.users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name, schema_name);

        EXECUTE format('
            CREATE TABLE %I.chat_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID NOT NULL REFERENCES %I.chat_sessions(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                content TEXT,
                tool_calls JSONB,
                tool_result JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )', schema_name, schema_name);

        -- Indexes
        EXECUTE format('CREATE INDEX idx_%I_devices_state ON %I.devices(state_id)', schema_name, schema_name);
        EXECUTE format('CREATE INDEX idx_%I_devices_policy ON %I.devices(current_policy_id)', schema_name, schema_name);
        EXECUTE format('CREATE INDEX idx_%I_devices_assigned ON %I.devices(assigned_action_id) WHERE assigned_action_id IS NOT NULL', schema_name, schema_name);
        EXECUTE format('CREATE INDEX idx_%I_ae_device ON %I.action_executions(device_id)', schema_name, schema_name);
        EXECUTE format('CREATE UNIQUE INDEX idx_%I_ae_cmd ON %I.action_executions(command_uuid)', schema_name, schema_name);
        EXECUTE format('CREATE INDEX idx_%I_ae_active ON %I.action_executions(status) WHERE status NOT IN (''ACTION_COMPLETED'', ''ACTION_FAILED'')', schema_name, schema_name);
        EXECUTE format('CREATE INDEX idx_%I_ms_device ON %I.milestones(device_id)', schema_name, schema_name);
        EXECUTE format('CREATE INDEX idx_%I_ms_created ON %I.milestones(created_at)', schema_name, schema_name);
        EXECUTE format('CREATE INDEX idx_%I_cs_user ON %I.chat_sessions(user_id)', schema_name, schema_name);
        EXECUTE format('CREATE INDEX idx_%I_cm_session ON %I.chat_messages(session_id, created_at)', schema_name, schema_name);
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS create_tenant_tables(TEXT);")
