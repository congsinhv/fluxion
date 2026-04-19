"""SQS batch consumer entry point for OEM worker Lambdas.

Replace the NotImplementedError body with real record processing logic
when scaffolding a real Lambda from this template.
"""

from __future__ import annotations

from typing import Any

from config import logger
from const import KEY_RECEIPT_HANDLE, KEY_RECORDS, KEY_SQS_BODY

# Raised inside the loop so callers (test suite, partial-batch failure handler)
# get a concrete exception type — not a bare NotImplementedError string literal.
_NOT_IMPLEMENTED_MSG = "_template oem worker — replace before deploy"


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    """Process a batch of SQS records.

    AWS Lambda invokes this function with a batch of up to 10 records.
    Each record is processed individually; raise to surface failures as
    partial-batch failures when ReportBatchItemFailures is enabled.

    Args:
        event: SQS event dict containing a ``Records`` list.
        context: AWS Lambda context object (provides aws_request_id, etc.).

    Raises:
        NotImplementedError: Always — template is not production-ready.
    """
    logger.info(
        "handler.invoked",
        extra={"request_id": getattr(context, "aws_request_id", None)},
    )
    for record in event.get(KEY_RECORDS, []):
        body: str = record.get(KEY_SQS_BODY, "")
        receipt_handle: str = record.get(KEY_RECEIPT_HANDLE, "")
        logger.debug(
            "handler.record_received",
            extra={"receipt_handle": receipt_handle, "body_length": len(body)},
        )
        # Replace with real logic when scaffolding from this template.
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
