"""Pydantic v2 DTOs for action_resolver — shaped to match schema.graphql exactly.

AppSync receives whatever model_dump() emits, so field names MUST match
GraphQL type field names (camelCase).

GraphQL types handled:

  type AssignActionResponse {
    executionId: ID!
    commandUuid: ID!
    status: ActionStatus!
  }

  type BulkAssignResponse {
    valid: [AssignActionResponse!]!
    failed: [BulkAssignError!]!
  }

  type BulkAssignError {
    deviceId: ID!
    reason: String!
  }

  type ActionLog {
    id: ID!
    batchId: ID!
    actionId: ID!
    created_by: String!
    totalDevices: Int!
    errorCount: Int!
    status: ActionLogStatus!
    created_at: AWSDateTime!
  }

  type ActionLogConnection {
    items: [ActionLog!]!
    nextToken: String
  }

  type ActionLogErrorReport {
    batchId: ID!
    url: String!
    expiresAt: AWSDateTime!
  }

  input AssignActionInput {
    deviceId: ID!
    actionId: ID!
    configuration: AWSJSON
    messageTemplateId: ID
  }

  input BulkAssignInput {
    deviceIds: [ID!]!
    actionId: ID!
    configuration: AWSJSON
    messageTemplateId: ID
  }

Notes:
  - ``ActionStatus`` here is just a string matching the DB enum
    (ACTION_PENDING at creation time).
  - ``batchId`` is internal only for assign mutations — not returned.
  - ``configuration`` is AWSJSON in schema (arbitrary JSON); accept as dict or None.
  - ActionLog has mixed snake_case (created_by, created_at) and camelCase fields —
    declared with matching Python attribute names so model_dump() emits the right keys.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

# ---------------------------------------------------------------------------
# Cursor input models (for listActionLogs / getActionLog / generateErrorReport)
# ---------------------------------------------------------------------------


class GetActionLogInput(BaseModel):
    """Input parsed from getActionLog(batchId: ID!) arguments."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    batchId: str


class ListActionLogsInput(BaseModel):
    """Input parsed from listActionLogs(limit, nextToken) arguments."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    limit: int = 20
    nextToken: str | None = None

    @field_validator("limit")
    @classmethod
    def _bound_limit(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError(f"limit must be between 1 and 100 (got {v})")
        return v


class GenerateErrorReportInput(BaseModel):
    """Input parsed from generateActionLogErrorReport(batchId: ID!) arguments."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    batchId: str


class BaseInput(BaseModel):
    """Strict input base — unknown fields rejected immediately."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BaseResponse(BaseModel):
    """Permissive response base — forward-compatible with new server fields."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class AssignActionInput(BaseInput):
    """Input for assignAction mutation.

    Attributes:
        deviceId:          Target device UUID.
        actionId:          Action UUID (must exist in tenant schema).
        configuration:     Arbitrary JSON payload forwarded to SQS consumer.
        messageTemplateId: Optional template UUID; when set, content is loaded
                           and injected as ``messageContent`` in the SQS envelope.
    """

    deviceId: UUID
    actionId: UUID
    configuration: dict[str, Any] | None = None
    messageTemplateId: UUID | None = None


class BulkAssignInput(BaseInput):
    """Input for assignBulkAction mutation.

    Attributes:
        deviceIds:         Non-empty list of device UUIDs (max 500).
        actionId:          Action UUID (must exist in tenant schema).
        configuration:     Arbitrary JSON payload forwarded to SQS consumer.
        messageTemplateId: Optional template UUID; same semantics as single assign.
    """

    deviceIds: list[UUID]
    actionId: UUID
    configuration: dict[str, Any] | None = None
    messageTemplateId: UUID | None = None

    @field_validator("deviceIds")
    @classmethod
    def validate_device_ids(cls, v: list[UUID]) -> list[UUID]:
        if not v:
            raise ValueError("deviceIds must contain at least one device")
        if len(v) > 500:
            raise ValueError(f"deviceIds exceeds maximum of 500 (got {len(v)})")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AssignActionResponse(BaseResponse):
    """Single-device assignment result — matches GraphQL AssignActionResponse.

    Attributes:
        executionId: ``action_executions.id`` UUID for this execution.
        commandUuid: ``action_executions.command_uuid`` — unique command identity
                     used by the action-trigger consumer.
        status:      Always ``ACTION_PENDING`` at creation time.
    """

    executionId: str  # UUID as string → GraphQL ID
    commandUuid: str  # UUID as string → GraphQL ID
    status: str  # ActionStatus enum value

    @classmethod
    def from_execution(
        cls,
        execution_id: str,
        command_uuid: str,
        status: str = "ACTION_PENDING",
    ) -> AssignActionResponse:
        """Build response from execution tuple fields."""
        return cls(executionId=execution_id, commandUuid=command_uuid, status=status)

    @classmethod
    def dump_execution(
        cls,
        execution_id: str,
        command_uuid: str,
        status: str = "ACTION_PENDING",
    ) -> dict[str, Any]:
        """Build and immediately serialize to dict."""
        return cls.from_execution(execution_id, command_uuid, status).model_dump()


class BulkAssignError(BaseResponse):
    """Per-device failure entry — matches GraphQL BulkAssignError.

    Attributes:
        deviceId: The device UUID that could not be assigned.
        reason:   Human-readable failure reason (includes error code prefix,
                  e.g. ``"DEVICE_BUSY: already assigned to action X"``).
    """

    deviceId: str  # UUID as string → GraphQL ID
    reason: str

    @classmethod
    def from_device(cls, device_id: str, reason: str) -> BulkAssignError:
        return cls(deviceId=device_id, reason=reason)


class BulkAssignResponse(BaseResponse):
    """Bulk assignment result — matches GraphQL BulkAssignResponse.

    Attributes:
        valid:  Successfully assigned devices with execution details.
        failed: Per-device failures (FSM mismatch, busy, not found).
    """

    valid: list[AssignActionResponse]
    failed: list[BulkAssignError]

    @classmethod
    def build(
        cls,
        valid: list[AssignActionResponse],
        failed: list[BulkAssignError],
    ) -> BulkAssignResponse:
        return cls(valid=valid, failed=failed)


# ---------------------------------------------------------------------------
# ActionLog response models (P1b)
# ---------------------------------------------------------------------------


class ActionLogResponse(BaseResponse):
    """Matches GraphQL type ActionLog.

    IMPORTANT: GraphQL field names are mixed snake_case + camelCase.
    Python attribute names MUST match GraphQL names so model_dump() emits
    the correct keys for AppSync:
      - snake_case:  created_by, created_at
      - camelCase:   id, batchId, actionId, totalDevices, errorCount, status

    model_config uses populate_by_name=True to allow construction by
    both alias and attribute name (psycopg dict_row uses snake names).
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    batchId: str
    actionId: str
    created_by: str
    totalDevices: int
    errorCount: int
    status: str
    created_at: str  # ISO-8601 string; psycopg returns datetime, handler converts

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ActionLogResponse:
        """Build from a psycopg dict_row (snake_case DB columns → mixed GQL fields).

        Expected keys: id, batch_id, action_id, created_by, total_devices,
                       error_count, status, created_at.
        """
        created_at = row["created_at"]
        return cls(
            id=str(row["id"]),
            batchId=str(row["batch_id"]),
            actionId=str(row["action_id"]),
            created_by=str(row["created_by"]),
            totalDevices=int(row["total_devices"]),
            errorCount=int(row["error_count"]),
            status=str(row["status"]),
            created_at=created_at.isoformat()
            if hasattr(created_at, "isoformat")
            else str(created_at),
        )


class ActionLogConnectionResponse(BaseResponse):
    """Matches GraphQL type ActionLogConnection."""

    items: list[ActionLogResponse]
    nextToken: str | None = None


class ActionLogErrorReportResponse(BaseResponse):
    """Matches GraphQL type ActionLogErrorReport."""

    batchId: str
    url: str
    expiresAt: str  # ISO-8601 datetime string (AWSDateTime)
