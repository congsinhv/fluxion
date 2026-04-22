"""Unit tests for cognito.py — covers all 4 admin methods via mocked boto3 client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import botocore.exceptions
import pytest


def _client_error(code: str) -> botocore.exceptions.ClientError:
    return botocore.exceptions.ClientError(
        {"Error": {"Code": code, "Message": code}},
        "operation",
    )


def _make_client(
    create_resp: Any = None,
    delete_exc: Exception | None = None,
    get_resp: Any = None,
    update_exc: Exception | None = None,
) -> MagicMock:
    client = MagicMock()
    if create_resp is not None:
        client.admin_create_user.return_value = create_resp
    if delete_exc:
        client.admin_delete_user.side_effect = delete_exc
    if get_resp is not None:
        client.admin_get_user.return_value = get_resp
    if update_exc:
        client.admin_update_user_attributes.side_effect = update_exc
    return client


# ---------------------------------------------------------------------------
# admin_create_user
# ---------------------------------------------------------------------------

class TestAdminCreateUser:
    def test_returns_sub(self) -> None:
        import cognito

        mock_resp = {
            "User": {
                "Attributes": [
                    {"Name": "sub", "Value": "abc-123"},
                    {"Name": "email", "Value": "x@example.com"},
                ]
            }
        }
        client = _make_client(create_resp=mock_resp)
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "us-east-1_test"):
            sub = cognito.admin_create_user("x@example.com", "TempPass1!")
        assert sub == "abc-123"
        client.admin_create_user.assert_called_once()

    def test_client_error_raises_cognito_error(self) -> None:
        import cognito
        from exceptions import CognitoError

        client = MagicMock()
        client.admin_create_user.side_effect = _client_error("UsernameExistsException")
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            with pytest.raises(CognitoError):
                cognito.admin_create_user("dup@example.com", "Pass1!")

    def test_missing_sub_raises_cognito_error(self) -> None:
        import cognito
        from exceptions import CognitoError

        mock_resp = {"User": {"Attributes": [{"Name": "email", "Value": "x@example.com"}]}}
        client = _make_client(create_resp=mock_resp)
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            with pytest.raises(CognitoError, match="sub attribute missing"):
                cognito.admin_create_user("x@example.com", "Pass1!")


# ---------------------------------------------------------------------------
# admin_delete_user
# ---------------------------------------------------------------------------

class TestAdminDeleteUser:
    def test_happy_path(self) -> None:
        import cognito

        client = MagicMock()
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            cognito.admin_delete_user("x@example.com")
        client.admin_delete_user.assert_called_once()

    def test_user_not_found_is_noop(self) -> None:
        """UserNotFoundException on delete is silently swallowed (idempotent rollback)."""
        import cognito

        client = MagicMock()
        client.admin_delete_user.side_effect = _client_error("UserNotFoundException")
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            cognito.admin_delete_user("gone@example.com")  # must not raise

    def test_other_error_raises(self) -> None:
        import cognito
        from exceptions import CognitoError

        client = MagicMock()
        client.admin_delete_user.side_effect = _client_error("InternalErrorException")
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            with pytest.raises(CognitoError):
                cognito.admin_delete_user("x@example.com")


# ---------------------------------------------------------------------------
# admin_get_user
# ---------------------------------------------------------------------------

class TestAdminGetUser:
    def test_returns_attrs_dict(self) -> None:
        import cognito

        mock_resp = {
            "UserAttributes": [
                {"Name": "sub", "Value": "abc-123"},
                {"Name": "custom:role", "Value": "ADMIN"},
            ]
        }
        client = _make_client(get_resp=mock_resp)
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            attrs = cognito.admin_get_user("x@example.com")
        assert attrs["custom:role"] == "ADMIN"
        assert attrs["sub"] == "abc-123"

    def test_user_not_found_raises_not_found_error(self) -> None:
        import cognito
        from exceptions import NotFoundError

        client = MagicMock()
        client.admin_get_user.side_effect = _client_error("UserNotFoundException")
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            with pytest.raises(NotFoundError):
                cognito.admin_get_user("missing@example.com")

    def test_other_error_raises_cognito_error(self) -> None:
        import cognito
        from exceptions import CognitoError

        client = MagicMock()
        client.admin_get_user.side_effect = _client_error("TooManyRequestsException")
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            with pytest.raises(CognitoError):
                cognito.admin_get_user("x@example.com")


# ---------------------------------------------------------------------------
# admin_update_user_attributes
# ---------------------------------------------------------------------------

class TestAdminUpdateUserAttributes:
    def test_happy_path(self) -> None:
        import cognito

        client = MagicMock()
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            cognito.admin_update_user_attributes("x@example.com", {"custom:role": "OPERATOR"})
        client.admin_update_user_attributes.assert_called_once()

    def test_user_not_found_raises_not_found_error(self) -> None:
        import cognito
        from exceptions import NotFoundError

        client = MagicMock()
        client.admin_update_user_attributes.side_effect = _client_error("UserNotFoundException")
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            with pytest.raises(NotFoundError):
                cognito.admin_update_user_attributes("gone@example.com", {"custom:role": "ADMIN"})

    def test_other_error_raises_cognito_error(self) -> None:
        import cognito
        from exceptions import CognitoError

        client = MagicMock()
        client.admin_update_user_attributes.side_effect = _client_error("InvalidParameterException")
        with patch("cognito._get_client", return_value=client), \
             patch("cognito.COGNITO_USER_POOL_ID", "pool"):
            with pytest.raises(CognitoError):
                cognito.admin_update_user_attributes("x@example.com", {"bad": "val"})
