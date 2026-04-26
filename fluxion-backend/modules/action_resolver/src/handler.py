"""Lambda entry point — AppSync field dispatch for action_resolver.

Fields handled:
  assignAction(input: AssignActionInput!)                        → AssignActionResponse!
  assignBulkAction(input: BulkAssignInput!)                      → BulkAssignResponse!
  getActionLog(batchId: ID!)                                     → ActionLog
  listActionLogs(limit: Int, nextToken: String)                  → ActionLogConnection!
  generateActionLogErrorReport(batchId: ID!)                     → ActionLogErrorReport!

Both assign mutations share a common implementation path (_assign_impl) that:
  1. Optionally loads a message template (validates is_active).
  2. Loads the action (validates existence).
  3. Validates devices via FSM state check (SQL JOIN).
  4. Writes batch_actions + batch_device_actions + action_executions
     in a single transaction with race-safe device locking.
  5. Sends one SQS message per locked device (post-commit; failures logged, not re-raised).

assignAction is a degenerate single-device case: raises on any per-device failure.
assignBulkAction collects per-device failures into failed[] and returns partial success.

Architectural note (GH-35 decision #9): batchId is internal SQS routing only;
it is never returned to the GraphQL caller. AssignActionResponse contains only
{executionId, commandUuid, status}.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from auth import Context, permission_required, validate_input
from config import logger
from csv_render import render_failed_devices_csv
from db import Database, ExecutionTuple, InvalidDevice
from exceptions import (
    ActionNotFoundError,
    BatchNotFoundError,
    DeviceAlreadyAssignedError,
    FluxionError,
    InvalidStateError,
    NotFoundError,
    SqsError,
    TemplateArchivedError,
    TemplateNotFoundError,
    UnknownFieldError,
)
from permissions import PERM_ACTION_EXECUTE, PERM_ACTIONLOG_READ
from s3 import presigned_get_url, put_csv
from schema_types import (
    ActionLogConnectionResponse,
    ActionLogErrorReportResponse,
    ActionLogResponse,
    AssignActionInput,
    AssignActionResponse,
    BulkAssignError,
    BulkAssignInput,
    BulkAssignResponse,
    GenerateErrorReportInput,
    GetActionLogInput,
    ListActionLogsInput,
)
from sqs import enqueue_action_trigger

FieldHandler = Callable[[dict[str, Any], Any, str], Any]


# ---------------------------------------------------------------------------
# Shared implementation
# ---------------------------------------------------------------------------


def _load_template_content(template_id: str, schema: str, db: Database) -> str:
    """Load and validate a message template, returning its content string.

    Args:
        template_id: UUID string of the message template.
        schema:      Tenant schema name.
        db:          Open Database instance.

    Returns:
        Template content string (plain text injected into SQS payload).

    Raises:
        TemplateNotFoundError: Template UUID does not exist.
        TemplateArchivedError: Template exists but is_active = FALSE.
    """
    row = db.load_message_template(template_id, schema)
    if row is None:
        raise TemplateNotFoundError(f"message template {template_id!r} not found")
    if not row["is_active"]:
        raise TemplateArchivedError(
            f"message template {template_id!r} is archived (is_active=FALSE)"
        )
    return str(row["content"])


def _build_sqs_envelope(
    *,
    batch_id: str,
    device_id: str,
    action_id: str,
    execution_id: str,
    command_uuid: str,
    configuration: dict[str, Any] | None,
    message_content: str | None,
    tenant_schema: str,
) -> dict[str, Any]:
    """Construct the SQS message envelope (GH-35 architectural decision #9)."""
    envelope: dict[str, Any] = {
        "batchId": batch_id,
        "deviceId": device_id,
        "actionId": action_id,
        "executionId": execution_id,
        "commandUuid": command_uuid,
        "configuration": configuration,
        "tenant_schema": tenant_schema,
    }
    if message_content is not None:
        envelope["messageContent"] = message_content
    return envelope


def _assign_impl(
    *,
    device_ids: list[str],
    action_id: str,
    configuration: dict[str, Any] | None,
    message_template_id: str | None,
    ctx: Context,
    correlation_id: str,
) -> tuple[list[ExecutionTuple], list[InvalidDevice]]:
    """Core assign logic shared by assignAction and assignBulkAction.

    Steps (all inside a single Database connection):
      1. Optionally load + validate message template.
      2. Load action → ActionNotFoundError if missing.
      3. Validate devices for FSM state match → split valid/invalid.
      4. create_batch_with_devices (single transaction + race-safe UPDATE).
      5. Devices missing from ExecutionTuple results (lost race) → DEVICE_BUSY failures.

    Args:
        device_ids:          List of device UUID strings to assign.
        action_id:           Action UUID string.
        configuration:       Optional JSON payload forwarded to SQS consumer.
        message_template_id: Optional template UUID string.
        ctx:                 Resolved caller context.
        correlation_id:      AWS request ID for tracing.

    Returns:
        (executions, all_invalid) where executions are successfully committed
        rows and all_invalid aggregates FSM + race failures.
    """
    schema = ctx.tenant_schema
    batch_id = str(uuid.uuid4())
    message_content: str | None = None

    with Database() as db:
        # Step 1: optionally load message template (whole-request failure).
        if message_template_id is not None:
            message_content = _load_template_content(message_template_id, schema, db)

        # Step 2: load action (whole-request failure).
        action_row = db.load_action(action_id, schema)
        if action_row is None:
            raise ActionNotFoundError(f"action {action_id!r} not found")

        # Step 3: classify devices by FSM state.
        valid_devices, invalid_devices = db.validate_devices_for_action(
            device_ids, action_id, schema
        )

        # Step 4: write batch in a single transaction with race-safe locking.
        executions = db.create_batch_with_devices(
            batch_id=batch_id,
            action_id=action_id,
            created_by=ctx.cognito_sub,
            valid_devices=valid_devices,
            schema=schema,
        )

    # Step 5: devices in valid_devices but absent from executions lost the race.
    executed_ids = {e.device_id for e in executions}
    race_losers: list[InvalidDevice] = [
        InvalidDevice(
            device_id=d.device_id,
            reason=f"DEVICE_BUSY: device {d.device_id} already has an assigned action",
        )
        for d in valid_devices
        if d.device_id not in executed_ids
    ]
    all_invalid = list(invalid_devices) + race_losers

    # Step 6: SQS enqueue per successfully committed device (post-commit).
    # Failures are logged and suppressed — DB commit already occurred.
    for ex in executions:
        envelope = _build_sqs_envelope(
            batch_id=batch_id,
            device_id=ex.device_id,
            action_id=action_id,
            execution_id=ex.execution_id,
            command_uuid=ex.command_uuid,
            configuration=configuration,
            message_content=message_content,
            tenant_schema=schema,
        )
        try:
            msg_id = enqueue_action_trigger(envelope)
            logger.info(
                "sqs.enqueued",
                extra={
                    "device_id": ex.device_id,
                    "execution_id": ex.execution_id,
                    "sqs_message_id": msg_id,
                    "correlation_id": correlation_id,
                },
            )
        except SqsError:
            # Post-commit SQS failure: row stays PENDING; ActionLog error report (P1b) flags it.
            logger.error(
                "sqs.enqueue_failed_post_commit",
                extra={
                    "device_id": ex.device_id,
                    "execution_id": ex.execution_id,
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                },
            )

    return executions, all_invalid


# ---------------------------------------------------------------------------
# Field handlers
# ---------------------------------------------------------------------------


@permission_required(PERM_ACTION_EXECUTE)
@validate_input(AssignActionInput, key="input")
def assign_action(
    _args: dict[str, Any], ctx: Context, correlation_id: str, inp: AssignActionInput
) -> dict[str, Any]:
    """Handle assignAction mutation — single device assignment.

    Raises a domain error if the device fails any validation (FSM mismatch,
    not found, already assigned). Does NOT return a partial-success response.

    Args:
        _args:          Raw arguments dict (pre-parsed via validate_input).
        ctx:            Resolved caller context (injected by permission_required).
        correlation_id: AWS request ID for tracing.
        inp:            Validated AssignActionInput.

    Returns:
        AssignActionResponse dict matching GraphQL type.

    Raises:
        ActionNotFoundError:       Action UUID not found.
        TemplateNotFoundError:     Template UUID not found.
        TemplateArchivedError:     Template is archived.
        NotFoundError:             Device UUID not found.
        InvalidStateError:         Device FSM state mismatch.
        DeviceAlreadyAssignedError: Device lost the race (already assigned).
    """
    device_id = str(inp.deviceId)
    action_id = str(inp.actionId)
    template_id = str(inp.messageTemplateId) if inp.messageTemplateId else None

    executions, all_invalid = _assign_impl(
        device_ids=[device_id],
        action_id=action_id,
        configuration=inp.configuration,
        message_template_id=template_id,
        ctx=ctx,
        correlation_id=correlation_id,
    )

    # Single-device path: raise on any per-device failure.
    if all_invalid:
        reason = all_invalid[0].reason
        if reason.startswith("DEVICE_NOT_FOUND"):
            raise NotFoundError(f"device {device_id} not found in tenant {ctx.tenant_schema}")
        if reason.startswith("INVALID_TRANSITION"):
            raise InvalidStateError(reason)
        if reason.startswith("DEVICE_BUSY"):
            raise DeviceAlreadyAssignedError(reason)
        # Fallback for unexpected reason strings.
        raise FluxionError(reason)

    if not executions:
        # Should not happen after all_invalid is empty, but guard for safety.
        raise DeviceAlreadyAssignedError(f"device {device_id} could not be assigned")

    ex = executions[0]
    return AssignActionResponse.dump_execution(
        execution_id=ex.execution_id,
        command_uuid=ex.command_uuid,
    )


@permission_required(PERM_ACTION_EXECUTE)
@validate_input(BulkAssignInput, key="input")
def assign_bulk_action(
    _args: dict[str, Any], ctx: Context, correlation_id: str, inp: BulkAssignInput
) -> dict[str, Any]:
    """Handle assignBulkAction mutation — N device assignments with partial success.

    Whole-request failures (ActionNotFoundError, TemplateNotFoundError,
    TemplateArchivedError) propagate as FluxionErrors and return error dicts.
    Per-device failures are collected into ``failed[]`` in the response.

    Args:
        _args:          Raw arguments dict (pre-parsed via validate_input).
        ctx:            Resolved caller context (injected by permission_required).
        correlation_id: AWS request ID for tracing.
        inp:            Validated BulkAssignInput.

    Returns:
        BulkAssignResponse dict matching GraphQL type.
    """
    device_ids = [str(d) for d in inp.deviceIds]
    action_id = str(inp.actionId)
    template_id = str(inp.messageTemplateId) if inp.messageTemplateId else None

    executions, all_invalid = _assign_impl(
        device_ids=device_ids,
        action_id=action_id,
        configuration=inp.configuration,
        message_template_id=template_id,
        ctx=ctx,
        correlation_id=correlation_id,
    )

    valid_responses = [
        AssignActionResponse.from_execution(
            execution_id=ex.execution_id,
            command_uuid=ex.command_uuid,
        )
        for ex in executions
    ]

    failed_responses = [
        BulkAssignError.from_device(device_id=inv.device_id, reason=inv.reason)
        for inv in all_invalid
    ]

    return BulkAssignResponse.build(valid=valid_responses, failed=failed_responses).model_dump()


# ---------------------------------------------------------------------------
# ActionLog read handlers (P1b)
# ---------------------------------------------------------------------------

_CSV_KEY_PREFIX = "action-log-errors"
_PRESIGN_TTL = 300  # 5 minutes


@permission_required(PERM_ACTIONLOG_READ)
@validate_input(GetActionLogInput)
def get_action_log(
    _args: dict[str, Any], ctx: Context, correlation_id: str, inp: GetActionLogInput
) -> dict[str, Any] | None:
    """Handle getActionLog(batchId: ID!) → ActionLog (null if not found).

    Returns None (AppSync null) when the batch doesn't exist — NOT an error.

    Args:
        _args:          Raw arguments dict.
        ctx:            Caller context.
        correlation_id: AWS request ID.
        inp:            Validated GetActionLogInput.

    Returns:
        ActionLogResponse dict or None if batch not found.
    """
    with Database() as db:
        row = db.get_action_log_by_batch_id(inp.batchId, ctx.tenant_schema)

    if row is None:
        return None

    return ActionLogResponse.from_row(row).model_dump()


@permission_required(PERM_ACTIONLOG_READ)
@validate_input(ListActionLogsInput)
def list_action_logs(
    _args: dict[str, Any], ctx: Context, correlation_id: str, inp: ListActionLogsInput
) -> dict[str, Any]:
    """Handle listActionLogs(limit, nextToken) → ActionLogConnection!.

    Args:
        _args:          Raw arguments dict.
        ctx:            Caller context.
        correlation_id: AWS request ID.
        inp:            Validated ListActionLogsInput.

    Returns:
        ActionLogConnectionResponse dict matching GraphQL type.
    """
    with Database() as db:
        rows, next_cursor = db.list_action_logs(
            limit=inp.limit,
            after_cursor=inp.nextToken,
            schema=ctx.tenant_schema,
        )

    items = [ActionLogResponse.from_row(r) for r in rows]
    return ActionLogConnectionResponse(items=items, nextToken=next_cursor).model_dump()


@permission_required(PERM_ACTIONLOG_READ)
@validate_input(GenerateErrorReportInput)
def generate_action_log_error_report(
    _args: dict[str, Any],
    ctx: Context,
    correlation_id: str,
    inp: GenerateErrorReportInput,
) -> dict[str, Any]:
    """Handle generateActionLogErrorReport(batchId: ID!) → ActionLogErrorReport!.

    Steps:
      1. Verify batch exists (BatchNotFoundError if missing).
      2. Fetch failed device rows.
      3. Render CSV (header-only if 0 failed rows — do NOT raise).
      4. Upload to S3 at action-log-errors/{batchId}.csv.
      5. Generate 5-min presigned GET URL.
      6. Return {batchId, url, expiresAt}.

    Args:
        _args:          Raw arguments dict.
        ctx:            Caller context.
        correlation_id: AWS request ID.
        inp:            Validated GenerateErrorReportInput.

    Returns:
        ActionLogErrorReportResponse dict matching GraphQL type.

    Raises:
        BatchNotFoundError: No batch_actions row for batchId.
        S3Error:            Upload or presign failed.
    """
    batch_id = inp.batchId

    with Database() as db:
        batch = db.get_action_log_by_batch_id(batch_id, ctx.tenant_schema)
        if batch is None:
            raise BatchNotFoundError(f"batch {batch_id!r} not found")

        failed_rows = db.get_failed_devices_for_batch(batch_id, ctx.tenant_schema)

    csv_bytes = render_failed_devices_csv(failed_rows)
    key = f"{_CSV_KEY_PREFIX}/{batch_id}.csv"

    put_csv(key, csv_bytes)

    url = presigned_get_url(key, ttl_seconds=_PRESIGN_TTL)
    expires_at = (datetime.now(UTC) + timedelta(seconds=_PRESIGN_TTL)).isoformat()

    logger.info(
        "action_log.error_report_generated",
        extra={
            "batch_id": batch_id,
            "key": key,
            "failed_count": len(failed_rows),
            "correlation_id": correlation_id,
        },
    )

    return ActionLogErrorReportResponse(
        batchId=batch_id,
        url=url,
        expiresAt=expires_at,
    ).model_dump()


# ---------------------------------------------------------------------------
# Dispatch table + entry point
# ---------------------------------------------------------------------------

FIELD_HANDLERS: dict[str, FieldHandler] = {
    "assignAction": assign_action,
    "assignBulkAction": assign_bulk_action,
    "getActionLog": get_action_log,
    "listActionLogs": list_action_logs,
    "generateActionLogErrorReport": generate_action_log_error_report,
}


def lambda_handler(event: dict[str, Any], context: Any) -> Any:
    """AppSync Lambda direct resolver entry point."""
    correlation_id: str = getattr(context, "aws_request_id", "local")
    field: str = event.get("info", {}).get("fieldName", "")

    logger.info("resolver.invoked", extra={"field": field, "correlation_id": correlation_id})

    try:
        handler = FIELD_HANDLERS.get(field)
        if handler is None:
            raise UnknownFieldError(f"no handler for field: {field!r}")
        result: Any = handler(event.get("arguments", {}), event, correlation_id)
        return result
    except FluxionError as exc:
        logger.warning(
            "resolver.error",
            extra={"field": field, "error_type": exc.code, "correlation_id": correlation_id},
        )
        return exc.to_appsync_error()
