"""Lambda entry point — AppSync field dispatch for upload_resolver.

Fields handled:
  uploadDevices(devices: [UploadDeviceInput!]!) → UploadResult!

uploadDevices implements bulk device intake:
  1. Parse + cap-validate the input (Pydantic, max 1000 devices).
  2. Per-device: check for empty serialNumber / udid → MISSING_FIELD.
  3. Request-level dedupe: track seen serials + udids → DUPLICATE_IN_REQUEST.
  4. Single DB query for existing keys → DUPLICATE_EXISTING_SERIAL / UDID.
  5. Enqueue one SQS message per accepted device (fire-and-forget post-dedupe).
  6. Return aggregate UploadResult.

Error codes used in UploadError.reason:
  MISSING_FIELD             — serialNumber or udid is empty / missing.
  DUPLICATE_IN_REQUEST      — same serialNumber or udid appears twice in the input.
  DUPLICATE_EXISTING_SERIAL — serialNumber already exists in device_informations.
  DUPLICATE_EXISTING_UDID   — udid already exists in device_informations.

Race note: the DB dedupe check and SQS enqueue are not atomic. The
upload-processor consumer is the sole writer to device_informations and MUST
handle UNIQUE-violation gracefully (its concern, not ours). Rare concurrent
uploads of the same serial from different callers may both pass the dedupe check
here; only one will succeed at the consumer level. This is an acceptable race for
human-ops workflows (GH-35 risk table).

SQS fire-and-forget: if SendMessage fails after the dedupe decision the device
is counted as accepted but will not be created. This matches the P1a pattern
(post-commit SQS failure is surfaced by the consumer, not the resolver).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from auth import Context, permission_required, validate_input
from config import logger
from db import Database
from exceptions import FluxionError, SqsError, UnknownFieldError
from permissions import PERM_UPLOAD_WRITE
from schema_types import (
    UploadDeviceInputModel,
    UploadDevicesInput,
    UploadErrorResponse,
    UploadResultResponse,
)
from sqs import enqueue_upload

FieldHandler = Callable[[dict[str, Any], Any, str], Any]


# ---------------------------------------------------------------------------
# Field handler
# ---------------------------------------------------------------------------


@permission_required(PERM_UPLOAD_WRITE)
@validate_input(UploadDevicesInput)
def upload_devices(
    _args: dict[str, Any],
    ctx: Context,
    correlation_id: str,
    inp: UploadDevicesInput,
) -> dict[str, Any]:
    """Handle uploadDevices mutation — bulk device intake with per-device error reporting.

    Returns an UploadResult even when all devices are rejected (no exception raised).

    Args:
        _args:          Raw arguments dict (pre-parsed via validate_input).
        ctx:            Resolved caller context (injected by permission_required).
        correlation_id: AWS request ID for tracing.
        inp:            Validated UploadDevicesInput.

    Returns:
        UploadResultResponse dict matching GraphQL type.
    """
    devices = inp.devices
    total = len(devices)

    # Short-circuit: empty input → trivial success.
    if total == 0:
        return UploadResultResponse.build(total=0, accepted=0, errors=[]).model_dump()

    errors: list[UploadErrorResponse] = []
    # (original_index, device) tuples that survived per-device checks.
    candidates: list[tuple[int, UploadDeviceInputModel]] = []

    seen_serials: set[str] = set()
    seen_udids: set[str] = set()

    # Pass 1: per-device validation + request-level dedupe.
    for i, device in enumerate(devices):
        serial = device.serialNumber
        udid = device.udid

        if not serial:
            errors.append(
                UploadErrorResponse.build(
                    index=i,
                    reason="MISSING_FIELD: serialNumber is required",
                    serial_number=None,
                )
            )
            continue

        if not udid:
            errors.append(
                UploadErrorResponse.build(
                    index=i,
                    reason="MISSING_FIELD: udid is required",
                    serial_number=serial,
                )
            )
            continue

        if serial in seen_serials:
            errors.append(
                UploadErrorResponse.build(
                    index=i,
                    reason=f"DUPLICATE_IN_REQUEST: serialNumber {serial!r} already in this batch",
                    serial_number=serial,
                )
            )
            continue

        if udid in seen_udids:
            errors.append(
                UploadErrorResponse.build(
                    index=i,
                    reason=f"DUPLICATE_IN_REQUEST: udid {udid!r} already in this batch",
                    serial_number=serial,
                )
            )
            continue

        seen_serials.add(serial)
        seen_udids.add(udid)
        candidates.append((i, device))

    # Pass 2: DB dedupe (single query for all candidate serials + udids).
    accepted: list[UploadDeviceInputModel] = []

    if candidates:
        candidate_serials = [d.serialNumber for _, d in candidates]
        candidate_udids = [d.udid for _, d in candidates]

        with Database() as db:
            existing = db.find_existing_device_keys(
                candidate_serials, candidate_udids, ctx.tenant_schema
            )

        for i, device in candidates:
            if device.serialNumber in existing.serials:
                errors.append(
                    UploadErrorResponse.build(
                        index=i,
                        reason=(
                            f"DUPLICATE_EXISTING_SERIAL: serialNumber {device.serialNumber!r}"
                            " already exists"
                        ),
                        serial_number=device.serialNumber,
                    )
                )
            elif device.udid in existing.udids:
                errors.append(
                    UploadErrorResponse.build(
                        index=i,
                        reason=f"DUPLICATE_EXISTING_UDID: udid {device.udid!r} already exists",
                        serial_number=device.serialNumber,
                    )
                )
            else:
                accepted.append(device)

    # Pass 3: SQS enqueue per accepted device (fire-and-forget).
    for device in accepted:
        envelope: dict[str, Any] = {
            "tenant_schema": ctx.tenant_schema,
            "serialNumber": device.serialNumber,
            "udid": device.udid,
            "name": device.name,
            "model": device.model,
            "osVersion": device.osVersion,
        }
        try:
            msg_id = enqueue_upload(envelope)
            logger.info(
                "sqs.upload_enqueued",
                extra={
                    "serial_number": device.serialNumber,
                    "sqs_message_id": msg_id,
                    "correlation_id": correlation_id,
                },
            )
        except SqsError:
            # Post-dedupe SQS failure: device is counted as accepted but will not
            # be created. Consumer is responsible for UNIQUE violations. See module
            # docstring for full rationale.
            logger.error(
                "sqs.upload_enqueue_failed",
                extra={
                    "serial_number": device.serialNumber,
                    "correlation_id": correlation_id,
                },
            )

    logger.info(
        "upload_devices.complete",
        extra={
            "total": total,
            "accepted": len(accepted),
            "rejected": len(errors),
            "correlation_id": correlation_id,
        },
    )

    return UploadResultResponse.build(
        total=total,
        accepted=len(accepted),
        errors=errors,
    ).model_dump()


# ---------------------------------------------------------------------------
# Dispatch table + entry point
# ---------------------------------------------------------------------------

FIELD_HANDLERS: dict[str, FieldHandler] = {
    "uploadDevices": upload_devices,
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
