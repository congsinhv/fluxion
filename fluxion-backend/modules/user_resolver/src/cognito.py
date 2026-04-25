"""Thin boto3 wrapper for Cognito admin operations used by user_resolver.

Four methods:
  - admin_create_user(email, temp_password) -> sub
  - admin_delete_user(username)             (rollback only)
  - admin_get_user(username) -> dict        (fetch custom:role attribute)
  - admin_update_user_attributes(username, attrs)  (future use)

MessageAction=SUPPRESS on create: Cognito does NOT send the welcome email
to newly created users — temp_password is generated internally and conveyed
through a separate channel. This prevents spam during automated provisioning.

NOTE: ``username`` in Cognito context is the user's email address, which is
used as the Cognito username (the pool uses email as the sign-in alias).
"""

from __future__ import annotations

from typing import Any

import boto3
import botocore.exceptions

from config import COGNITO_USER_POOL_ID, logger
from exceptions import CognitoError, NotFoundError

# Module-level client; re-used across warm invocations.
_client: Any = None


def _get_client() -> Any:
    global _client  # noqa: PLW0603
    if _client is None:
        _client = boto3.client("cognito-idp")
    return _client


def admin_create_user(email: str, temp_password: str) -> str:
    """Create a Cognito user and return the assigned ``sub`` (UUID).

    Uses MessageAction=SUPPRESS so no welcome email is sent.
    The caller is responsible for communicating the temp_password out-of-band.

    Args:
        email:         User's email address (also used as Cognito username).
        temp_password: Temporary password meeting pool policy requirements.

    Returns:
        Cognito user ``sub`` UUID string.

    Raises:
        CognitoError: Cognito API call failed (UsernameExistsException, etc.).
    """
    client = _get_client()
    try:
        resp = client.admin_create_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=email,
            TemporaryPassword=temp_password,
            MessageAction="SUPPRESS",
        )
    except botocore.exceptions.ClientError as exc:
        code = exc.response["Error"]["Code"]
        logger.error("cognito.admin_create_user_failed", extra={"email": email, "code": code})
        raise CognitoError(f"admin_create_user failed: {code}") from exc

    # Extract sub from UserAttributes list
    attrs: list[dict[str, str]] = resp["User"]["Attributes"]
    sub_map = {a["Name"]: a["Value"] for a in attrs}
    sub = sub_map.get("sub", "")
    if not sub:
        raise CognitoError("admin_create_user: sub attribute missing in response")
    return sub


def admin_delete_user(username: str) -> None:
    """Delete a Cognito user by username (email). Used only for rollback.

    Args:
        username: Cognito username (email) of the user to delete.

    Raises:
        CognitoError: Deletion failed for a reason other than UserNotFound.
    """
    client = _get_client()
    try:
        client.admin_delete_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=username,
        )
    except botocore.exceptions.ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "UserNotFoundException":
            # Already gone — rollback is a no-op.
            logger.warning("cognito.admin_delete_user_not_found", extra={"username": username})
            return
        logger.error("cognito.admin_delete_user_failed", extra={"username": username, "code": code})
        raise CognitoError(f"admin_delete_user failed: {code}") from exc


def admin_get_user(username: str) -> dict[str, str]:
    """Fetch user attributes dict from Cognito by username (email).

    Used to read the ``custom:role`` attribute that lives in Cognito only
    (not persisted in accesscontrol.users).

    Args:
        username: Cognito username (email).

    Returns:
        Dict of attribute name → value, e.g. ``{"sub": "...", "custom:role": "ADMIN"}``.

    Raises:
        NotFoundError: UserNotFoundException from Cognito.
        CognitoError:  Other Cognito API failures.
    """
    client = _get_client()
    try:
        resp = client.admin_get_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=username,
        )
    except botocore.exceptions.ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "UserNotFoundException":
            raise NotFoundError(f"cognito user not found: {username!r}") from exc
        logger.error("cognito.admin_get_user_failed", extra={"username": username, "code": code})
        raise CognitoError(f"admin_get_user failed: {code}") from exc

    attrs: list[dict[str, str]] = resp.get("UserAttributes", [])
    return {a["Name"]: a["Value"] for a in attrs}


def admin_update_user_attributes(username: str, attrs: dict[str, str]) -> None:
    """Update arbitrary Cognito user attributes (future use).

    Args:
        username: Cognito username (email).
        attrs:    Dict of attribute name → value to set.

    Raises:
        NotFoundError: UserNotFoundException from Cognito.
        CognitoError:  Other Cognito API failures.
    """
    client = _get_client()
    user_attrs = [{"Name": k, "Value": v} for k, v in attrs.items()]
    try:
        client.admin_update_user_attributes(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=username,
            UserAttributes=user_attrs,
        )
    except botocore.exceptions.ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "UserNotFoundException":
            raise NotFoundError(f"cognito user not found: {username!r}") from exc
        logger.error(
            "cognito.admin_update_user_attributes_failed",
            extra={"username": username, "code": code},
        )
        raise CognitoError(f"admin_update_user_attributes failed: {code}") from exc
