"""Lambda entry point — AppSync field dispatch.

Shape (design-patterns.md §4):
  1. Read fieldName from event["info"]["fieldName"].
  2. Look up FIELD_HANDLERS dispatch table.
  3. Call handler(event["arguments"], ctx, correlation_id).
  4. Catch FluxionError → AppSync error response.

When scaffolding a real Lambda:
  - Populate FIELD_HANDLERS with real field handler functions.
  - Remove the _handle_not_implemented stub.
  - Handlers decorated with @permission_required receive (args, ctx, cid).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from config import POWERTOOLS_SERVICE_NAME
from exceptions import FluxionError, UnknownFieldError

logger = logging.getLogger(POWERTOOLS_SERVICE_NAME)

# ---------------------------------------------------------------------------
# Field handler registry — replace stubs when scaffolding a real Lambda.
# Each value must be callable as: handler(args, ctx, correlation_id) -> Any
# ---------------------------------------------------------------------------

FieldHandler = Callable[[dict[str, Any], Any, str], Any]

FIELD_HANDLERS: dict[str, FieldHandler] = {
    # "getDevice": handle_get_device,   # example — uncomment when scaffolding
}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AppSync Lambda direct resolver entry point.

    Args:
        event: AppSync resolver event with ``info.fieldName`` and ``arguments``.
        context: AWS Lambda context object.

    Returns:
        Field handler result or AppSync error dict on ``FluxionError``.
    """
    correlation_id: str = getattr(context, "aws_request_id", "local")
    field: str = event.get("info", {}).get("fieldName", "")

    logger.info(
        "resolver.invoked",
        extra={"field": field, "correlation_id": correlation_id},
    )

    try:
        handler = FIELD_HANDLERS.get(field)
        if handler is None:
            raise UnknownFieldError(f"no handler for field: {field!r}")
        result: dict[str, Any] = handler(event.get("arguments", {}), event, correlation_id)
        return result
    except FluxionError as exc:
        logger.warning(
            "resolver.error",
            extra={"field": field, "error_type": exc.code, "correlation_id": correlation_id},
        )
        return exc.to_appsync_error()
