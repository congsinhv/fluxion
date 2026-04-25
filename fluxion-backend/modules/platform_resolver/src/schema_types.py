"""Pydantic v2 DTOs for platform_resolver — shaped to match schema.graphql exactly.

AppSync receives whatever model_dump() emits, so field names MUST match GraphQL
type field names (camelCase).

Queries return flat lists (not connection objects — schema uses [T!]!):
  listStates(serviceTypeId: Int): [State!]!
  listPolicies(serviceTypeId: Int): [Policy!]!
  listActions(fromStateId: Int, serviceTypeId: Int): [Action!]!
  listServices: [Service!]!

Mutations return single objects:
  updateState(id: Int!, input: UpdateStateInput!): State!
  updatePolicy(id: Int!, input: UpdatePolicyInput!): Policy!
  updateAction(id: ID!, input: UpdateActionInput!): Action!
  updateService(id: Int!, input: UpdateServiceInput!): Service!

Table mapping (per-tenant schema, from migration 4768d32c8037):
  states    → State (id SMALLINT, name)
  policies  → Policy (id SMALLINT, name, state_id, service_type_id, color)
  actions   → Action (id UUID, name, action_type_id, from_state_id, service_type_id, apply_policy_id, configuration)
  services  → Service (id SMALLINT, name, is_enabled)
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseInput(BaseModel):
    """Strict input base — unknown fields rejected immediately."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BaseResponse(BaseModel):
    """Permissive response base — forward-compatible with new server fields."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Response types — match GraphQL type field names
# ---------------------------------------------------------------------------


class StateResponse(BaseResponse):
    """Maps states table → GraphQL State type."""

    id: int
    name: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> StateResponse:
        return cls(id=int(row["id"]), name=row["name"])

    @classmethod
    def dump_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return cls.from_row(row).model_dump()


class ServiceResponse(BaseResponse):
    """Maps services table → GraphQL Service type."""

    id: int
    name: str
    isEnabled: bool

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ServiceResponse:
        return cls(id=int(row["id"]), name=row["name"], isEnabled=bool(row["is_enabled"]))

    @classmethod
    def dump_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return cls.from_row(row).model_dump()


class PolicyResponse(BaseResponse):
    """Maps policies table → GraphQL Policy type.

    Note: nested `state: State!` and `applyPolicy: Policy!` resolvers are
    not handled here — Lambda returns flat scalars only.
    """

    id: int
    name: str
    stateId: int
    serviceTypeId: int
    color: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PolicyResponse:
        return cls(
            id=int(row["id"]),
            name=row["name"],
            stateId=int(row["state_id"]),
            serviceTypeId=int(row["service_type_id"]),
            color=row.get("color"),
        )

    @classmethod
    def dump_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return cls.from_row(row).model_dump()


class ActionResponse(BaseResponse):
    """Maps actions table → GraphQL Action type.

    id is UUID, serialised as str to match GraphQL ID scalar.
    Nested `fromState`, `applyPolicy` resolvers omitted (flat scalars only).
    """

    id: str  # UUID → GraphQL ID
    name: str
    actionTypeId: int
    fromStateId: int | None = None
    serviceTypeId: int | None = None
    applyPolicyId: int
    configuration: str | None = None  # JSONB serialised as string for AppSync AWSJSON

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ActionResponse:
        cfg = row.get("configuration")
        return cls(
            id=str(row["id"]),
            name=row["name"],
            actionTypeId=int(row["action_type_id"]),
            fromStateId=int(row["from_state_id"]) if row.get("from_state_id") is not None else None,
            serviceTypeId=int(row["service_type_id"]) if row.get("service_type_id") is not None else None,
            applyPolicyId=int(row["apply_policy_id"]),
            configuration=json.dumps(cfg) if cfg is not None else None,
        )

    @classmethod
    def dump_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return cls.from_row(row).model_dump()


# ---------------------------------------------------------------------------
# List query input models (all args are optional filters)
# ---------------------------------------------------------------------------


class ListStatesInput(BaseInput):
    """Arguments for listStates(serviceTypeId: Int)."""

    serviceTypeId: int | None = None


class ListPoliciesInput(BaseInput):
    """Arguments for listPolicies(serviceTypeId: Int)."""

    serviceTypeId: int | None = None


class ListActionsInput(BaseInput):
    """Arguments for listActions(fromStateId: Int, serviceTypeId: Int)."""

    fromStateId: int | None = None
    serviceTypeId: int | None = None


# listServices has no input args — no model needed.


# ---------------------------------------------------------------------------
# Update mutation input models — PATCH semantics (exclude_unset)
# ---------------------------------------------------------------------------


class UpdateStateInput(BaseInput):
    """Input for updateState — name is required per schema."""

    name: str = Field(..., min_length=1)


class UpdatePolicyInput(BaseInput):
    """Input for updatePolicy — all fields optional (at least one must be set)."""

    name: str | None = None
    stateId: int | None = None
    serviceTypeId: int | None = None
    color: str | None = None


class UpdateActionInput(BaseInput):
    """Input for updateAction — all fields optional (at least one must be set)."""

    name: str | None = None
    actionTypeId: int | None = None
    fromStateId: int | None = None
    serviceTypeId: int | None = None
    applyPolicyId: int | None = None
    configuration: str | None = None


class UpdateServiceInput(BaseInput):
    """Input for updateService — all fields optional (at least one must be set)."""

    name: str | None = None
    isEnabled: bool | None = None
