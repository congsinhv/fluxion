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

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from utils import to_iso


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

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DeviceInformationResponse:
        ext = row.get("ext_fields")
        return cls(
            id=str(row["di_id"]),
            deviceId=str(row["id"]),
            serialNumber=row["serial_number"] or "",
            udid=row["udid"] or "",
            name=row.get("di_name"),
            model=row.get("model"),
            osVersion=row.get("os_version"),
            batteryLevel=row.get("battery_level"),
            wifiMac=row.get("wifi_mac"),
            isSupervised=row.get("is_supervised"),
            lastCheckinAt=to_iso(row.get("last_checkin_at")),
            extFields=json.dumps(ext) if ext is not None else None,
        )

    @classmethod
    def dump_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return cls.from_row(row).model_dump()


# ---------------------------------------------------------------------------
# Device — id + timestamps + nested information; nullable complex fields omitted
# (AppSync emits null for missing nullable fields — KISS)
# ---------------------------------------------------------------------------


class DeviceResponse(BaseResponse):
    id: str
    createdAt: str
    updatedAt: str
    information: DeviceInformationResponse | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DeviceResponse:
        info: DeviceInformationResponse | None = None
        if row.get("di_id") is not None:
            info = DeviceInformationResponse.from_row(row)
        return cls(
            id=str(row["id"]),
            createdAt=to_iso(row["created_at"]) or "",
            updatedAt=to_iso(row["updated_at"]) or "",
            information=info,
        )

    @classmethod
    def dump_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return cls.from_row(row).model_dump()


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

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> MilestoneResponse:
        ext = row.get("ext_fields")
        return cls(
            id=str(row["id"]),
            deviceId=str(row["device_id"]),
            assignedActionId=str(row["assigned_action_id"]) if row.get("assigned_action_id") else None,
            policyId=row.get("policy_id"),
            createdAt=to_iso(row["created_at"]) or "",
            extFields=json.dumps(ext) if ext is not None else None,
        )

    @classmethod
    def dump_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        return cls.from_row(row).model_dump()


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
