"""Utility functions for checkin_handler."""

import json
import re
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from config import APPSYNC_ENDPOINT, logger

_session = boto3.Session()
_region = _session.region_name or "ap-southeast-1"


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format (alphanumeric + underscore only) to prevent SQL injection."""
    if not re.match(r"^[a-zA-Z0-9_]+$", tenant_id):
        raise ValueError("Invalid tenant_id format")
    return tenant_id


def call_appsync_mutation(query: str, variables: dict) -> dict:
    """Call AppSync GraphQL mutation with IAM (SigV4) authentication.

    Uses botocore SigV4Auth to sign the HTTP POST request.
    The Lambda execution role must have appsync:GraphQL permission.
    """
    payload = json.dumps({"query": query, "variables": variables}).encode()

    request = AWSRequest(
        method="POST",
        url=APPSYNC_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    # Resolve credentials per-call to handle IAM role rotation on warm containers
    credentials = _session.get_credentials().get_frozen_credentials()
    SigV4Auth(credentials, "appsync", _region).add_auth(request)

    req = urllib.request.Request(
        APPSYNC_ENDPOINT,
        data=payload,
        headers=dict(request.headers),
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        response_body = json.loads(resp.read())

    if "errors" in response_body:
        logger.warning("AppSync mutation returned errors", extra={"errors": response_body["errors"]})

    return response_body
