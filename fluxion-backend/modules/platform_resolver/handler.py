"""Lambda handler for platform_resolver — config queries + update mutations."""

from aws_lambda_powertools.event_handler import AppSyncResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from config import logger, tracer
from db import DBConnection
from exceptions import FluxionError, ForbiddenError, NotFoundError
from utils import (
    format_action,
    format_policy,
    format_service,
    format_state,
    validate_tenant_id,
)

app = AppSyncResolver()


def _get_tenant(app_instance: AppSyncResolver) -> str:
    """Extract and validate tenant_id from JWT claims."""
    tenant_id = app_instance.current_event.identity.claims["custom:tenant_id"]
    return validate_tenant_id(tenant_id)


def _require_admin(app_instance: AppSyncResolver) -> None:
    """Raise ForbiddenError if caller is not ADMIN."""
    role = app_instance.current_event.identity.claims.get("custom:role")
    if role != "ADMIN":
        raise ForbiddenError("Only ADMIN can modify config")


# ─── Config queries ──────────────────────────────────────────────────────────────


@app.resolver(type_name="Query", field_name="listStates")
def list_states() -> list[dict]:
    tenant = _get_tenant(app)
    try:
        rows = DBConnection.list_states(schema_name=tenant)
        return [format_state(r) for r in rows]
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in listStates")
        raise


@app.resolver(type_name="Query", field_name="listPolicies")
def list_policies(serviceTypeId: int | None = None) -> list[dict]:  # noqa: N803
    tenant = _get_tenant(app)
    try:
        rows = DBConnection.list_policies(schema_name=tenant, service_type_id=serviceTypeId)
        return [format_policy(r) for r in rows]
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in listPolicies")
        raise


@app.resolver(type_name="Query", field_name="listActions")
def list_actions(
    fromStateId: int | None = None, serviceTypeId: int | None = None  # noqa: N803
) -> list[dict]:
    tenant = _get_tenant(app)
    try:
        rows = DBConnection.list_actions(
            schema_name=tenant,
            from_state_id=fromStateId,
            service_type_id=serviceTypeId,
        )
        return [format_action(r) for r in rows]
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in listActions")
        raise


@app.resolver(type_name="Query", field_name="listServices")
def list_services() -> list[dict]:
    tenant = _get_tenant(app)
    try:
        rows = DBConnection.list_services(schema_name=tenant)
        return [format_service(r) for r in rows]
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in listServices")
        raise


# ─── Config mutations (ADMIN only) ──────────────────────────────────────────────


@app.resolver(type_name="Mutation", field_name="updateState")
def update_state(id: int, input: dict) -> dict:
    _require_admin(app)
    tenant = _get_tenant(app)
    try:
        row = DBConnection.update_state(schema_name=tenant, state_id=id, name=input["name"])
        if not row:
            raise NotFoundError("State", id)
        return format_state(row)
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in updateState")
        raise


@app.resolver(type_name="Mutation", field_name="updatePolicy")
def update_policy(id: int, input: dict) -> dict:
    _require_admin(app)
    tenant = _get_tenant(app)
    try:
        row = DBConnection.update_policy(schema_name=tenant, policy_id=id, input_data=input)
        if not row:
            raise NotFoundError("Policy", id)
        return format_policy(row)
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in updatePolicy")
        raise


@app.resolver(type_name="Mutation", field_name="updateAction")
def update_action(id: str, input: dict) -> dict:
    _require_admin(app)
    tenant = _get_tenant(app)
    try:
        row = DBConnection.update_action(schema_name=tenant, action_id=id, input_data=input)
        if not row:
            raise NotFoundError("Action", id)
        return format_action(row)
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in updateAction")
        raise


@app.resolver(type_name="Mutation", field_name="updateService")
def update_service(id: int, input: dict) -> dict:
    _require_admin(app)
    tenant = _get_tenant(app)
    try:
        row = DBConnection.update_service(schema_name=tenant, service_id=id, input_data=input)
        if not row:
            raise NotFoundError("Service", id)
        return format_service(row)
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in updateService")
        raise


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda entry point — dispatches to AppSyncResolver."""
    logger.debug("Event received", extra={"event": event})
    return app.resolve(event, context)
