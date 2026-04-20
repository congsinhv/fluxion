"""Lambda entry point skeleton.

Replace the body with field dispatch (AppSync) or SQS record loop when
scaffolding a real Lambda from this template. See design-patterns.md §4.

Import style: no `src.` prefix — Dockerfile copies src/ flat into
LAMBDA_TASK_ROOT; pytest pythonpath = ["src"] mirrors this.
"""

from __future__ import annotations

from typing import Any

from config import logger
from exceptions import FluxionError


def lambda_handler(_event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AppSync / SQS entry point.

    Replace the body with field dispatch or SQS record loop when scaffolding
    a real Lambda from this template. Rename _event to event once the body
    reads from it.

    Args:
        _event: AppSync resolver event or SQS event dict (unused in template).
        context: AWS Lambda context object.

    Returns:
        AppSync response dict or SQS batch response.

    Raises:
        NotImplementedError: Always — template is not deployable as-is.
    """
    logger.info(
        "handler.invoked",
        extra={"request_id": getattr(context, "aws_request_id", None)},
    )
    try:
        raise NotImplementedError("_template handler — replace before deploy")
    except FluxionError as exc:
        return exc.to_appsync_error()
