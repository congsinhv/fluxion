"""Pydantic v2 DTOs for upload_resolver — shaped to match schema.graphql exactly.

AppSync receives whatever model_dump() emits, so field names MUST match
GraphQL type field names (camelCase).

GraphQL types handled:

  type UploadResult {
    totalRequested: Int!
    accepted: Int!
    rejected: Int!
    errors: [UploadError!]
  }

  type UploadError {
    index: Int!
    serialNumber: String
    reason: String!
  }

  input UploadDeviceInput {
    serialNumber: String!
    udid: String!
    name: String
    model: String
    osVersion: String
  }

Notes:
  - ``UploadDeviceInputModel`` does NOT validate empty strings in Pydantic —
    per-device empty checks are done in the handler to produce ``MISSING_FIELD``
    errors with the correct original index position. Pydantic enforces shape only.
  - ``UploadDevicesInput.devices`` cap of 1000 is a whole-request failure via
    field_validator (mirrors BulkAssignInput.deviceIds <= 500 in action_resolver).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class BaseInput(BaseModel):
    """Strict input base — unknown fields rejected immediately."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BaseResponse(BaseModel):
    """Permissive response base — forward-compatible with new server fields."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class UploadDeviceInputModel(BaseInput):
    """Single device record from the UploadDeviceInput GraphQL input type.

    Attributes:
        serialNumber: Device serial number (non-empty validated at handler level).
        udid:         Device UDID (non-empty validated at handler level).
        name:         Optional display name.
        model:        Optional hardware model string.
        osVersion:    Optional OS version string.

    Note:
        Empty-string checks for serialNumber and udid are intentionally deferred
        to the handler so that per-device MISSING_FIELD errors carry the correct
        original index. Pydantic only enforces field presence and type here.
    """

    serialNumber: str
    udid: str
    name: str | None = None
    model: str | None = None
    osVersion: str | None = None


class UploadDevicesInput(BaseModel):
    """Wrapper input for the uploadDevices mutation.

    Attributes:
        devices: List of device records to upload (max 1000).

    Note:
        Uses extra="ignore" (not "forbid") because AppSync passes the raw
        arguments dict directly (no "input" key wrapper for this mutation).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    devices: list[UploadDeviceInputModel]

    @field_validator("devices")
    @classmethod
    def _cap_devices(cls, v: list[UploadDeviceInputModel]) -> list[UploadDeviceInputModel]:
        if len(v) > 1000:
            raise ValueError(f"devices exceeds maximum of 1000 (got {len(v)})")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class UploadErrorResponse(BaseResponse):
    """Per-device failure entry — matches GraphQL UploadError.

    Attributes:
        index:        Zero-based position of the device in the original input list.
        serialNumber: Device serial number, or None when missing-field error occurs
                      before the serial was determined.
        reason:       Human-readable failure reason with error code prefix,
                      e.g. ``"MISSING_FIELD: serialNumber is required"``.
    """

    index: int
    serialNumber: str | None = None
    reason: str

    @classmethod
    def build(
        cls,
        index: int,
        reason: str,
        serial_number: str | None = None,
    ) -> UploadErrorResponse:
        """Construct from handler fields."""
        return cls(index=index, serialNumber=serial_number, reason=reason)


class UploadResultResponse(BaseResponse):
    """Bulk upload result — matches GraphQL UploadResult.

    Attributes:
        totalRequested: Total number of devices in the input list.
        accepted:       Devices that passed validation and were enqueued.
        rejected:       Devices that failed validation (len(errors)).
        errors:         Per-device failure entries (null when empty is acceptable
                        per schema: ``errors: [UploadError!]`` without ``!``).
    """

    totalRequested: int
    accepted: int
    rejected: int
    errors: list[UploadErrorResponse]

    @classmethod
    def build(
        cls,
        total: int,
        accepted: int,
        errors: list[UploadErrorResponse],
    ) -> UploadResultResponse:
        """Construct from counts and error list."""
        return cls(
            totalRequested=total,
            accepted=accepted,
            rejected=len(errors),
            errors=errors,
        )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize, converting nested UploadErrorResponse to dicts."""
        d = super().model_dump(**kwargs)
        d["errors"] = [e.model_dump() for e in self.errors]
        return d
