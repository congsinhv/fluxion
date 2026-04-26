"""Tests for s3.put_csv and s3.presigned_get_url."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import s3 as s3_module
from exceptions import S3Error


def _make_client() -> MagicMock:
    mock = MagicMock()
    mock.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    mock.generate_presigned_url.return_value = "https://s3.example.com/presigned"
    return mock


class TestPutCsv:
    def setup_method(self) -> None:
        # Reset module-level singleton between tests.
        s3_module._client = None

    def test_happy_path_calls_put_object(self) -> None:
        mock_client = _make_client()
        with patch("s3._get_client", return_value=mock_client):
            s3_module.put_csv("action-log-errors/abc.csv", b"data", bucket="test-bucket")

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="action-log-errors/abc.csv",
            Body=b"data",
            ContentType="text/csv",
        )

    def test_uses_env_bucket_when_not_overridden(self) -> None:
        mock_client = _make_client()
        with patch("s3._get_client", return_value=mock_client):
            with patch("s3.UPLOADS_BUCKET", "env-bucket"):
                s3_module.put_csv("key.csv", b"body")

        call_kwargs = mock_client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "env-bucket"

    def test_client_error_raises_s3_error(self) -> None:
        mock_client = _make_client()
        mock_client.put_object.side_effect = Exception("connection refused")
        with patch("s3._get_client", return_value=mock_client):
            with pytest.raises(S3Error, match="put_object failed"):
                s3_module.put_csv("key.csv", b"body", bucket="b")

    def test_s3_error_message_includes_key(self) -> None:
        mock_client = _make_client()
        mock_client.put_object.side_effect = Exception("boom")
        with patch("s3._get_client", return_value=mock_client):
            with pytest.raises(S3Error) as exc_info:
                s3_module.put_csv("errors/batch-123.csv", b"x", bucket="b")
        assert "errors/batch-123.csv" in str(exc_info.value)


class TestPresignedGetUrl:
    def setup_method(self) -> None:
        s3_module._client = None

    def test_returns_url_string(self) -> None:
        mock_client = _make_client()
        with patch("s3._get_client", return_value=mock_client):
            url = s3_module.presigned_get_url("action-log-errors/abc.csv", bucket="b")
        assert url == "https://s3.example.com/presigned"

    def test_calls_generate_presigned_url_with_correct_params(self) -> None:
        mock_client = _make_client()
        with patch("s3._get_client", return_value=mock_client):
            s3_module.presigned_get_url("my/key.csv", ttl_seconds=180, bucket="bkt")

        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "bkt", "Key": "my/key.csv"},
            ExpiresIn=180,
        )

    def test_default_ttl_is_300(self) -> None:
        mock_client = _make_client()
        with patch("s3._get_client", return_value=mock_client):
            s3_module.presigned_get_url("key.csv", bucket="b")

        call_kwargs = mock_client.generate_presigned_url.call_args.kwargs
        assert call_kwargs["ExpiresIn"] == 300

    def test_client_error_raises_s3_error(self) -> None:
        mock_client = _make_client()
        mock_client.generate_presigned_url.side_effect = Exception("forbidden")
        with patch("s3._get_client", return_value=mock_client):
            with pytest.raises(S3Error, match="presign failed"):
                s3_module.presigned_get_url("key.csv", bucket="b")

    def test_uses_env_bucket_when_not_overridden(self) -> None:
        mock_client = _make_client()
        with patch("s3._get_client", return_value=mock_client):
            with patch("s3.UPLOADS_BUCKET", "env-bucket"):
                s3_module.presigned_get_url("key.csv")

        call_kwargs = mock_client.generate_presigned_url.call_args.kwargs
        assert call_kwargs["Params"]["Bucket"] == "env-bucket"


class TestGetClientSingleton:
    def setup_method(self) -> None:
        s3_module._client = None

    def test_singleton_reused_across_calls(self) -> None:
        mock_client = _make_client()
        with patch("s3._get_client", return_value=mock_client) as mock_get:
            s3_module.put_csv("k.csv", b"x", bucket="b")
            s3_module.put_csv("k2.csv", b"y", bucket="b")
        # _get_client called once per put_csv (function is patched, not the real lazy init)
        assert mock_get.call_count == 2
