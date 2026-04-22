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


class ServiceResponse(BaseResponse):
    """Maps services table → GraphQL Service type."""

    id: int
    name: str
    isEnabled: bool


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
