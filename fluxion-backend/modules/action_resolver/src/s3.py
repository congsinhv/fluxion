"""Thin S3 wrapper for action_resolver — CSV upload + presigned GET URL.

Client is lazily initialized (same pattern as sqs.py) to avoid import-time
AWS SDK initialization in test environments.

Errors from boto3 are caught and re-raised as S3Error so callers get a
uniform FluxionError.

Security note: log only the S3 key — never the presigned URL (may contain
credentials as query parameters).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from config import UPLOADS_BUCKET, logger
from exceptions import S3Error

if TYPE_CHECKING:
    import botocore.exceptions  # noqa: F401  (type-checking import only)

# Module-level lazy singleton — avoids boto3 import at cold-start in tests.
_client: Any = None


def _get_client() -> Any:
    """Return (or create) the module-level boto3 S3 client."""
    global _client  # noqa: PLW0603
    if _client is None:
        import boto3  # deferred — not available in unit-test environments

        _client = boto3.client("s3")
    return _client


def put_csv(key: str, body: bytes, bucket: str | None = None) -> None:
    """Upload CSV bytes to S3.

    Args:
        key:    S3 object key (e.g. ``"action-log-errors/{batchId}.csv"``).
        body:   Raw bytes to upload (UTF-8 + BOM CSV).
        bucket: Override bucket name; defaults to ``UPLOADS_BUCKET`` env var.

    Raises:
        S3Error: boto3 ClientError or any unexpected exception during upload.
    """
    effective_bucket = bucket or UPLOADS_BUCKET
    client = _get_client()
    try:
        client.put_object(
            Bucket=effective_bucket,
            Key=key,
            Body=body,
            ContentType="text/csv",
        )
        logger.info("s3.put_csv_success", extra={"bucket": effective_bucket, "key": key})
    except Exception as exc:
        # Catch botocore.exceptions.ClientError and any other boto3 error.
        logger.exception("s3.put_csv_failed", extra={"bucket": effective_bucket, "key": key})
        raise S3Error(f"S3 put_object failed for key {key!r}: {exc}") from exc


def presigned_get_url(
    key: str,
    ttl_seconds: int = 300,
    bucket: str | None = None,
) -> str:
    """Generate a pre-signed GET URL for an S3 object.

    Args:
        key:         S3 object key.
        ttl_seconds: URL expiry in seconds (default 5 minutes).
        bucket:      Override bucket name; defaults to ``UPLOADS_BUCKET`` env var.

    Returns:
        Pre-signed HTTPS URL string.

    Raises:
        S3Error: boto3 ClientError or any unexpected exception during presign.
    """
    effective_bucket = bucket or UPLOADS_BUCKET
    client = _get_client()
    try:
        url: str = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": effective_bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )
        # Log key only — never log the URL (contains signed credentials).
        logger.info(
            "s3.presigned_url_generated",
            extra={"bucket": effective_bucket, "key": key, "ttl_seconds": ttl_seconds},
        )
        return url
    except Exception as exc:
        logger.exception("s3.presign_failed", extra={"bucket": effective_bucket, "key": key})
        raise S3Error(f"S3 presign failed for key {key!r}: {exc}") from exc
