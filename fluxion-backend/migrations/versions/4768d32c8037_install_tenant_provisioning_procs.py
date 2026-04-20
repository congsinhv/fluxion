"""Install tenant provisioning procedures.

Revision ID: 4768d32c8037
Revises: 7124824094ea
Create Date: 2026-04-20

Installs two PL/pgSQL procedures in `public` that own tenant DDL + seed:

  * `public.create_tenant_schema(text)` — CREATE SCHEMA + 16 business tables
    per wiki T5 ER Diagram (§3.6) + indexes (§3.6.3).
  * `public.create_default_tenant_data(text)` — seed FSM config
    (services/states/policies/actions), brands, tacs, message_templates
    per wiki T5-DeviceFSM §3.4.5.

Tenants are provisioned by calling both procs with a schema_name. The
`accesscontrol` schema (0001) owns cross-tenant identity; per-tenant
business data lives in `{schema_name}.*`.

chat_sessions.user_id is BIGINT with no cross-schema FK — app layer
validates the reference to accesscontrol.users.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "4768d32c8037"
down_revision = "7124824094ea"
branch_labels = None
depends_on = None


# Matches accesscontrol.tenants.ck_tenants_schema_name_format (0001).
_SCHEMA_NAME_REGEX = r"^[a-z][a-z0-9_]{0,39}$"


CREATE_TENANT_SCHEMA_PROC = f"""
CREATE OR REPLACE PROCEDURE public.create_tenant_schema(p_schema_name TEXT)
LANGUAGE plpgsql AS $proc$
DECLARE
    v_schema TEXT := p_schema_name;
BEGIN
    IF v_schema !~ '{_SCHEMA_NAME_REGEX}' THEN
        RAISE EXCEPTION 'invalid tenant schema_name: %', v_schema
            USING ERRCODE = '22023';
    END IF;

    IF v_schema IN ('public','information_schema','pg_catalog','pg_toast','accesscontrol') THEN
        RAISE EXCEPTION 'reserved schema_name: %', v_schema
            USING ERRCODE = '22023';
    END IF;

    EXECUTE format('CREATE SCHEMA %I', v_schema);

    -- FSM config (wiki T5-DeviceFSM §3.4.5) — SMALLINT PKs, explicit seeds.
    EXECUTE format($ddl$
        CREATE TABLE %I.services (
            id         SMALLINT PRIMARY KEY,
            name       VARCHAR(50) NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_services_name UNIQUE (name)
        )
    $ddl$, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.states (
            id         SMALLINT PRIMARY KEY,
            name       VARCHAR(50) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_states_name UNIQUE (name)
        )
    $ddl$, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.policies (
            id              SMALLINT PRIMARY KEY,
            name            VARCHAR(100) NOT NULL,
            service_type_id SMALLINT REFERENCES %I.services(id),
            state_id        SMALLINT REFERENCES %I.states(id),
            color           VARCHAR(6),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema, v_schema, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.actions (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name            VARCHAR(100) NOT NULL,
            action_type_id  SMALLINT NOT NULL,
            from_state_id   SMALLINT REFERENCES %I.states(id),
            service_type_id SMALLINT REFERENCES %I.services(id),
            apply_policy_id SMALLINT REFERENCES %I.policies(id),
            configuration   JSONB,
            ext_fields      JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema, v_schema, v_schema, v_schema);

    -- devices (wiki §3.6.2.2) — Fluxion business fields only.
    EXECUTE format($ddl$
        CREATE TABLE %I.devices (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            state_id           SMALLINT NOT NULL REFERENCES %I.states(id) DEFAULT 1,
            current_policy_id  SMALLINT REFERENCES %I.policies(id),
            assigned_action_id UUID REFERENCES %I.actions(id),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema, v_schema, v_schema, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.device_informations (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            device_id       UUID NOT NULL UNIQUE REFERENCES %I.devices(id) ON DELETE CASCADE,
            serial_number   VARCHAR(50) UNIQUE NOT NULL,
            udid            VARCHAR(50) UNIQUE NOT NULL,
            name            VARCHAR(200),
            model           VARCHAR(100),
            os_version      VARCHAR(20),
            battery_level   REAL,
            wifi_mac        VARCHAR(20),
            is_supervised   BOOLEAN DEFAULT FALSE,
            last_checkin_at TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ext_fields      JSONB
        )
    $ddl$, v_schema, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.device_tokens (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            device_id    UUID NOT NULL UNIQUE REFERENCES %I.devices(id) ON DELETE CASCADE,
            push_token   BYTEA NOT NULL,
            push_magic   VARCHAR(200) NOT NULL,
            unlock_token BYTEA,
            topic        VARCHAR(200) NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.action_executions (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            device_id    UUID NOT NULL REFERENCES %I.devices(id),
            action_id    UUID NOT NULL REFERENCES %I.actions(id),
            command_uuid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            status       VARCHAR(20) NOT NULL DEFAULT 'ACTION_PENDING',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ext_fields   JSONB
        )
    $ddl$, v_schema, v_schema, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.milestones (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            device_id          UUID NOT NULL REFERENCES %I.devices(id),
            assigned_action_id UUID REFERENCES %I.actions(id),
            policy_id          SMALLINT REFERENCES %I.policies(id),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ext_fields         JSONB
        )
    $ddl$, v_schema, v_schema, v_schema, v_schema);

    -- chat_sessions.user_id: BIGINT to accesscontrol.users; cross-schema FK omitted.
    EXECUTE format($ddl$
        CREATE TABLE %I.chat_sessions (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.chat_messages (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id  UUID NOT NULL REFERENCES %I.chat_sessions(id) ON DELETE CASCADE,
            role        VARCHAR(20) NOT NULL,
            content     TEXT,
            tool_calls  JSONB,
            tool_result JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_chat_messages_role CHECK (role IN ('user','assistant','tool'))
        )
    $ddl$, v_schema, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.message_templates (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                   VARCHAR(255) NOT NULL,
            content                TEXT NOT NULL,
            notification_type      VARCHAR(20) NOT NULL,
            is_active              BOOLEAN NOT NULL DEFAULT TRUE,
            notification_icon_path VARCHAR(512) NOT NULL,
            header_icon_path       VARCHAR(512) NOT NULL,
            additional_icon_path   VARCHAR(512) NOT NULL,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_message_templates_type
                CHECK (notification_type IN ('FULLSCREEN','POPUP'))
        )
    $ddl$, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.brands (
            id         SERIAL PRIMARY KEY,
            name       VARCHAR(255) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.tacs (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tac_code          VARCHAR(20) NOT NULL UNIQUE,
            provisioning_type VARCHAR(50) NOT NULL,
            brand_id          INT REFERENCES %I.brands(id) ON DELETE SET NULL,
            model             VARCHAR(100),
            marketing_name    VARCHAR(255),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.batch_actions (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id      UUID NOT NULL UNIQUE,
            action_id     UUID NOT NULL REFERENCES %I.actions(id),
            created_by    VARCHAR(255) NOT NULL,
            total_devices INT NOT NULL,
            status        VARCHAR(20) NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema, v_schema);

    EXECUTE format($ddl$
        CREATE TABLE %I.batch_device_actions (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id      UUID NOT NULL
                REFERENCES %I.batch_actions(batch_id) ON DELETE CASCADE,
            device_id     UUID NOT NULL REFERENCES %I.devices(id),
            status        VARCHAR(20) NOT NULL,
            error_code    VARCHAR(100),
            error_message TEXT,
            started_at    TIMESTAMPTZ,
            finished_at   TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    $ddl$, v_schema, v_schema, v_schema);

    -- Indexes (wiki §3.6.3)
    EXECUTE format('CREATE INDEX idx_devices_state_id ON %I.devices(state_id)', v_schema);
    EXECUTE format(
        'CREATE INDEX idx_devices_current_policy_id ON %I.devices(current_policy_id)', v_schema
    );
    EXECUTE format(
        $q$CREATE INDEX idx_devices_assigned ON %I.devices(assigned_action_id)
           WHERE assigned_action_id IS NOT NULL$q$,
        v_schema
    );
    EXECUTE format(
        'CREATE UNIQUE INDEX idx_di_device_id ON %I.device_informations(device_id)', v_schema
    );
    EXECUTE format(
        'CREATE UNIQUE INDEX idx_dt_device_id ON %I.device_tokens(device_id)', v_schema
    );
    EXECUTE format(
        'CREATE INDEX idx_ae_device_id ON %I.action_executions(device_id)', v_schema
    );
    EXECUTE format(
        'CREATE UNIQUE INDEX idx_ae_command_uuid ON %I.action_executions(command_uuid)', v_schema
    );
    EXECUTE format(
        $q$CREATE INDEX idx_ae_active ON %I.action_executions(status)
           WHERE status NOT IN ('ACTION_COMPLETED', 'ACTION_FAILED')$q$,
        v_schema
    );
    EXECUTE format('CREATE INDEX idx_milestones_device_id ON %I.milestones(device_id)', v_schema);
    EXECUTE format(
        'CREATE INDEX idx_milestones_created_at ON %I.milestones(created_at)', v_schema
    );
    EXECUTE format(
        'CREATE INDEX idx_chat_sessions_user_id ON %I.chat_sessions(user_id)', v_schema
    );
    EXECUTE format(
        'CREATE INDEX idx_chat_messages_session ON %I.chat_messages(session_id, created_at)',
        v_schema
    );
    EXECUTE format(
        'CREATE INDEX idx_message_templates_notification_type '
        'ON %I.message_templates(notification_type)',
        v_schema
    );
    EXECUTE format(
        'CREATE INDEX idx_message_templates_is_active ON %I.message_templates(is_active)',
        v_schema
    );
    EXECUTE format('CREATE INDEX idx_tacs_tac_code ON %I.tacs(tac_code)', v_schema);
    EXECUTE format('CREATE INDEX idx_tacs_brand_id ON %I.tacs(brand_id)', v_schema);
    EXECUTE format('CREATE INDEX idx_batch_actions_status ON %I.batch_actions(status)', v_schema);
    EXECUTE format(
        'CREATE INDEX idx_batch_actions_created_at ON %I.batch_actions(created_at DESC)',
        v_schema
    );
    EXECUTE format(
        'CREATE INDEX idx_batch_device_actions_batch_id ON %I.batch_device_actions(batch_id)',
        v_schema
    );
    EXECUTE format(
        'CREATE INDEX idx_batch_device_actions_status ON %I.batch_device_actions(status)',
        v_schema
    );
END;
$proc$;
"""


CREATE_DEFAULT_TENANT_DATA_PROC = f"""
CREATE OR REPLACE PROCEDURE public.create_default_tenant_data(p_schema_name TEXT)
LANGUAGE plpgsql AS $proc$
DECLARE
    v_schema TEXT := p_schema_name;
BEGIN
    IF v_schema !~ '{_SCHEMA_NAME_REGEX}' THEN
        RAISE EXCEPTION 'invalid tenant schema_name: %', v_schema
            USING ERRCODE = '22023';
    END IF;

    EXECUTE format($seed$
        INSERT INTO %I.services (id, name, is_enabled) VALUES
            (1, 'Inventory',    TRUE),
            (2, 'Supply Chain', FALSE),
            (3, 'Postpaid',     TRUE)
    $seed$, v_schema);

    EXECUTE format($seed$
        INSERT INTO %I.states (id, name) VALUES
            (1, 'Idle'),
            (2, 'Registered'),
            (3, 'Enrolled'),
            (4, 'Active'),
            (5, 'Locked'),
            (6, 'Released')
    $seed$, v_schema);

    EXECUTE format($seed$
        INSERT INTO %I.policies (id, name, state_id, service_type_id) VALUES
            (1, 'Idle',       1, 1),
            (2, 'Registered', 2, 3),
            (3, 'Enrolled',   3, 3),
            (4, 'Active',     4, 3),
            (5, 'Locked',     5, 3),
            (6, 'Released',   6, 3)
    $seed$, v_schema);

    EXECUTE format($seed$
        INSERT INTO %I.actions (name, action_type_id, from_state_id,
                                apply_policy_id, service_type_id) VALUES
            ('Upload',        1, NULL, 1, NULL),
            ('Register',      2, 1,    2, 1),
            ('Checkin',       3, 2,    3, 3),
            ('Activate',      4, 3,    4, 3),
            ('Lock',          5, 4,    5, 3),
            ('Unlock',        6, 5,    4, 3),
            ('Send Message',  7, 4,    4, 3),
            ('Lock Message',  8, 5,    5, 3),
            ('Release',       9, 1,    6, 3),
            ('Release',       9, 2,    6, 3),
            ('Release',       9, 3,    6, 3),
            ('Release',       9, 4,    6, 3),
            ('Release',       9, 5,    6, 3),
            ('Deregister',   10, 4,    1, 3),
            ('Deregister',   10, 5,    1, 3)
    $seed$, v_schema);

    EXECUTE format($seed$
        INSERT INTO %I.brands (name) VALUES ('iPhone')
    $seed$, v_schema);

    EXECUTE format($seed$
        INSERT INTO %I.tacs (tac_code, provisioning_type, brand_id, model, marketing_name)
        SELECT '35387910', 'Apple', b.id, 'A2650', 'iPhone 14 Pro'
        FROM %I.brands b WHERE b.name = 'iPhone'
    $seed$, v_schema, v_schema);

    EXECUTE format($seed$
        INSERT INTO %I.message_templates
            (name, content, notification_type, is_active,
             notification_icon_path, header_icon_path, additional_icon_path)
        VALUES
            ('lock_popup',
             'Thiết bị đã bị khóa. Vui lòng liên hệ CSKH để được hỗ trợ.',
             'POPUP', TRUE,
             '/icons/notification-default.png',
             '/icons/header-default.png',
             '/icons/additional-default.png'),
            ('lock_fullscreen',
             'THIẾT BỊ ĐÃ BỊ KHÓA. Vui lòng liên hệ CSKH.',
             'FULLSCREEN', TRUE,
             '/icons/notification-default.png',
             '/icons/header-default.png',
             '/icons/additional-default.png'),
            ('reminder_popup',
             'Bạn có khoản thanh toán sắp đến hạn.',
             'POPUP', TRUE,
             '/icons/notification-default.png',
             '/icons/header-default.png',
             '/icons/additional-default.png')
    $seed$, v_schema);
END;
$proc$;
"""


def upgrade() -> None:
    """Install create_tenant_schema + create_default_tenant_data procs."""
    op.execute(CREATE_TENANT_SCHEMA_PROC)
    op.execute(CREATE_DEFAULT_TENANT_DATA_PROC)


def downgrade() -> None:
    """Drop both procs."""
    op.execute("DROP PROCEDURE IF EXISTS public.create_default_tenant_data(TEXT)")
    op.execute("DROP PROCEDURE IF EXISTS public.create_tenant_schema(TEXT)")
