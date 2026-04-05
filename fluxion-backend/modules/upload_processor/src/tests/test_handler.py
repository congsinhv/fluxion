"""Tests for upload_processor handler — mock DBConnection, test SQS batch processing."""

import json
from unittest.mock import MagicMock, patch

# Mock config before importing handler (Lambda Powertools needs env vars)
with patch.dict(
    "os.environ",
    {
        "POWERTOOLS_SERVICE_NAME": "test",
        "POWERTOOLS_TRACE_DISABLED": "1",
    },
):
    from db import DBConnection
    from handler import handler


def _make_sqs_event(records: list[dict]) -> dict:
    """Build a minimal SQS event with message bodies."""
    return {
        "Records": [
            {
                "messageId": f"msg-{i}",
                "body": json.dumps(rec),
            }
            for i, rec in enumerate(records)
        ],
    }


def _device_msg(serial: str, udid: str, tenant: str = "test_tenant") -> dict:
    return {
        "serialNumber": serial,
        "udid": udid,
        "name": "iPhone 15",
        "model": "iPhone15,2",
        "osVersion": "17.0",
        "tenantId": tenant,
    }


class TestUploadProcessor:
    @patch.object(DBConnection, "insert_device_with_info")
    def test_happy_path(self, mock_insert):
        """Single record → device inserted, no batch failures."""
        mock_insert.return_value = "device-001"
        event = _make_sqs_event([_device_msg("SN1", "UD1")])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        mock_insert.assert_called_once_with(
            schema_name="test_tenant",
            serial_number="SN1",
            udid="UD1",
            name="iPhone 15",
            model="iPhone15,2",
            os_version="17.0",
        )

    @patch.object(DBConnection, "insert_device_with_info")
    def test_duplicate_returns_none(self, mock_insert):
        """Duplicate serial → returns None, no error, no batch failure."""
        mock_insert.return_value = None
        event = _make_sqs_event([_device_msg("SN-DUP", "UD-DUP")])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        mock_insert.assert_called_once()

    @patch.object(DBConnection, "insert_device_with_info")
    def test_multiple_records(self, mock_insert):
        """3 records all succeed → empty batchItemFailures."""
        mock_insert.side_effect = ["dev-1", "dev-2", "dev-3"]
        event = _make_sqs_event([
            _device_msg("SN1", "UD1"),
            _device_msg("SN2", "UD2"),
            _device_msg("SN3", "UD3"),
        ])
        result = handler(event, MagicMock())

        assert result["batchItemFailures"] == []
        assert mock_insert.call_count == 3

    @patch.object(DBConnection, "insert_device_with_info")
    def test_partial_failure(self, mock_insert):
        """2 records, second fails DB → batchItemFailures has 1 entry."""
        mock_insert.side_effect = ["dev-1", Exception("DB error")]
        event = _make_sqs_event([
            _device_msg("SN1", "UD1"),
            _device_msg("SN2", "UD2"),
        ])
        result = handler(event, MagicMock())

        assert len(result["batchItemFailures"]) == 1
        assert result["batchItemFailures"][0]["itemIdentifier"] == "msg-1"

    @patch.object(DBConnection, "insert_device_with_info")
    def test_invalid_tenant_id(self, mock_insert):
        """Invalid tenant → ValueError → batch failure."""
        event = _make_sqs_event([_device_msg("SN1", "UD1", tenant="bad;tenant")])
        result = handler(event, MagicMock())

        assert len(result["batchItemFailures"]) == 1
        mock_insert.assert_not_called()
