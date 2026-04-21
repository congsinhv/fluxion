"""Unit test for the smoketest Lambda handler."""

from http import HTTPStatus

from handler import lambda_handler


def test_lambda_handler_returns_ok() -> None:
    result = lambda_handler({}, object())
    assert result["statusCode"] == HTTPStatus.OK
    assert result["body"] == "smoketest ok"
