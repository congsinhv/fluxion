"""SQS event key constants for OEM worker Lambdas.

Use these constants instead of bare string literals when reading from the
SQS event dict to avoid typo-driven runtime errors.
"""

from __future__ import annotations

# Top-level SQS event keys
KEY_RECORDS = "Records"

# Per-record keys inside each element of event["Records"]
KEY_SQS_BODY = "body"
KEY_RECEIPT_HANDLE = "receiptHandle"

# Lambda context attribute — present on the real AWS context object
KEY_AWS_REQUEST_ID = "aws_request_id"
