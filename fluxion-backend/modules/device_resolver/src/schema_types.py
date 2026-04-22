"""Pydantic v2 DTOs for device_resolver — shaped to match schema.graphql exactly.

AppSync receives whatever model_dump() emits, so field names here MUST match
the GraphQL type field names (camelCase). Keys absent from the response are
treated as null by AppSync for nullable fields.

Table mapping (tenant schema, from migration 4768d32c8037):
  devices            → Device (id, state_id, current_policy_id, assigned_action_id, ...)
  device_informations → DeviceInformation (serial_number, udid, name, ...)
  milestones         → Milestone (id, device_id, assigned_action_id, policy_id, ...)
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
# DeviceInformation — maps device_informations table columns to GQL camelCase
# ---------------------------------------------------------------------------


class DeviceInformationResponse(BaseResponse):
    id: str
    deviceId: str
    serialNumber: str
    udid: str
    name: str | None = None
    model: str | None = None
    osVersion: str | None = None
    batteryLevel: float | None = None
    wifiMac: str | None = None
    isSupervised: bool | None = None
    lastCheckinAt: str | None = None
    extFields: str | None = None  # JSONB serialised as string for AppSync AWSJSON


# ---------------------------------------------------------------------------
# Device — id + timestamps + nested information; nullable complex fields omitted
# (AppSync emits null for missing nullable fields — KISS)
# ---------------------------------------------------------------------------


class DeviceResponse(BaseResponse):
    id: str
    createdAt: str
    updatedAt: str
    information: DeviceInformationResponse | None = None


# ---------------------------------------------------------------------------
# DeviceConnection — flat shape matching schema.graphql DeviceConnection
# ---------------------------------------------------------------------------


class DeviceConnectionResponse(BaseResponse):
    items: list[DeviceResponse] = Field(default_factory=list)
    nextToken: str | None = None
    totalCount: int = 0


# ---------------------------------------------------------------------------
# Milestone — maps milestones table; GQL type Milestone
# ---------------------------------------------------------------------------


class MilestoneResponse(BaseResponse):
    id: str
    deviceId: str
    assignedActionId: str | None = None
    policyId: int | None = None
    createdAt: str
    extFields: str | None = None


# ---------------------------------------------------------------------------
# MilestoneConnection — flat shape matching schema.graphql MilestoneConnection
# ---------------------------------------------------------------------------


class MilestoneConnectionResponse(BaseResponse):
    items: list[MilestoneResponse] = Field(default_factory=list)
    nextToken: str | None = None


# ---------------------------------------------------------------------------
# Input models for the three query fields
# ---------------------------------------------------------------------------


class DeviceFilterInput(BaseInput):
    """Optional filter for listDevices — schema input DeviceFilter."""

    stateId: int | None = None
    policyId: int | None = None
    search: str | None = None


class ListDevicesInput(BaseInput):
    """Arguments for listDevices(filter, limit, nextToken)."""

    filter: DeviceFilterInput | None = None
    limit: int = Field(default=20, ge=1, le=100)
    nextToken: str | None = None


class GetDeviceInput(BaseInput):
    """Arguments for getDevice(id)."""

    id: str


class GetDeviceHistoryInput(BaseInput):
    """Arguments for getDeviceHistory(deviceId, limit, nextToken)."""

    deviceId: str
    limit: int = Field(default=20, ge=1, le=100)
    nextToken: str | None = None
