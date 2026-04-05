"""Lambda handler for upload_resolver — uploadDevices."""

from aws_lambda_powertools.event_handler import AppSyncResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from config import SQS_QUEUE_URL, logger, tracer
from const import (
    MAX_UPLOAD_DEVICES,
    REASON_DUPLICATE_SERIAL_BATCH,
    REASON_DUPLICATE_UDID_BATCH,
    REASON_EMPTY_SERIAL,
    REASON_EMPTY_UDID,
    REASON_SERIAL_EXISTS,
    REASON_UDID_EXISTS,
)
from db import DBConnection
from exceptions import FluxionError
from utils import get_tenant, send_message

app = AppSyncResolver()


@app.resolver(type_name="Mutation", field_name="uploadDevices")
def upload_devices(devices: list[dict]) -> dict:
    tenant = get_tenant(app)
    total = len(devices)

    if total > MAX_UPLOAD_DEVICES:
        raise FluxionError(f"Exceeds max upload limit of {MAX_UPLOAD_DEVICES}", "VALIDATION_ERROR")

    errors = []
    accepted_indices = set(range(total))

    # Stage 1: Format validation — serialNumber + udid non-empty
    for i, dev in enumerate(devices):
        if not dev.get("serialNumber", "").strip():
            errors.append({"index": i, "serialNumber": dev.get("serialNumber"), "reason": REASON_EMPTY_SERIAL})
            accepted_indices.discard(i)
        elif not dev.get("udid", "").strip():
            errors.append({"index": i, "serialNumber": dev.get("serialNumber"), "reason": REASON_EMPTY_UDID})
            accepted_indices.discard(i)

    # Stage 2: Intra-batch duplicate detection
    seen_serials: dict[str, int] = {}
    seen_udids: dict[str, int] = {}
    for i in sorted(accepted_indices):
        serial = devices[i]["serialNumber"]
        udid = devices[i]["udid"]
        if serial in seen_serials:
            errors.append({"index": i, "serialNumber": serial, "reason": REASON_DUPLICATE_SERIAL_BATCH})
            accepted_indices.discard(i)
        elif udid in seen_udids:
            errors.append({"index": i, "serialNumber": serial, "reason": REASON_DUPLICATE_UDID_BATCH})
            accepted_indices.discard(i)
        else:
            seen_serials[serial] = i
            seen_udids[udid] = i

    # Stage 3: DB duplicate check (only for remaining accepted)
    if accepted_indices:
        try:
            serials = [devices[i]["serialNumber"] for i in accepted_indices]
            udids = [devices[i]["udid"] for i in accepted_indices]
            existing = DBConnection.find_existing_identifiers(tenant, serials, udids)

            existing_serials = {r["serial_number"] for r in existing}
            existing_udids = {r["udid"] for r in existing}

            for i in sorted(accepted_indices):
                serial = devices[i]["serialNumber"]
                udid = devices[i]["udid"]
                if serial in existing_serials:
                    errors.append({"index": i, "serialNumber": serial, "reason": REASON_SERIAL_EXISTS})
                    accepted_indices.discard(i)
                elif udid in existing_udids:
                    errors.append({"index": i, "serialNumber": serial, "reason": REASON_UDID_EXISTS})
                    accepted_indices.discard(i)
        except FluxionError:
            raise
        except Exception:
            logger.exception("Unexpected error during DB duplicate check")
            raise

    # Enqueue accepted devices to SQS
    for i in accepted_indices:
        dev = devices[i]
        message_body = {
            "serialNumber": dev["serialNumber"],
            "udid": dev["udid"],
            "name": dev.get("name"),
            "model": dev.get("model"),
            "osVersion": dev.get("osVersion"),
            "tenantId": tenant,
        }
        send_message(SQS_QUEUE_URL, message_body)

    # Sort errors by index for consistent output
    errors.sort(key=lambda e: e["index"])

    return {
        "totalRequested": total,
        "accepted": len(accepted_indices),
        "rejected": total - len(accepted_indices),
        "errors": errors if errors else None,
    }


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda entry point — dispatches to AppSyncResolver."""
    logger.debug("Event received", extra={"event": event})
    return app.resolve(event, context)
