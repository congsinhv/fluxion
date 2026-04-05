"""Tests for upload_resolver handler — mock DBConnection + SQS, test validation pipeline."""

from unittest.mock import MagicMock, patch

# Mock config before importing handler (Lambda Powertools needs env vars)
with patch.dict(
    "os.environ",
    {
        "POWERTOOLS_SERVICE_NAME": "test",
        "POWERTOOLS_TRACE_DISABLED": "1",
        "SQS_QUEUE_URL": "https://sqs.ap-southeast-1.amazonaws.com/123456789/test-queue",
        "AWS_DEFAULT_REGION": "ap-southeast-1",
    },
):
    from db import DBConnection
    from handler import app

TENANT = "test_tenant"


def _make_appsync_event(field_name: str, arguments: dict, type_name: str = "Mutation") -> dict:
    """Build a minimal AppSync resolver event."""
    return {
        "typeName": type_name,
        "fieldName": field_name,
        "arguments": arguments,
        "identity": {
            "claims": {
                "custom:tenant_id": TENANT,
                "custom:role": "ADMIN",
                "sub": "cognito-sub-123",
            },
            "sub": "cognito-sub-123",
        },
        "info": {
            "fieldName": field_name,
            "parentTypeName": type_name,
            "selectionSetList": [],
        },
    }


def _device(serial: str, udid: str, name: str = "iPhone") -> dict:
    return {"serialNumber": serial, "udid": udid, "name": name, "model": "iPhone15,2", "osVersion": "17.0"}


class TestUploadDevices:
    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_happy_path(self, mock_db, mock_send):
        """3 valid devices → accepted=3, rejected=0, SQS called 3x."""
        mock_db.return_value = []
        devices = [_device("SN1", "UD1"), _device("SN2", "UD2"), _device("SN3", "UD3")]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["totalRequested"] == 3
        assert result["accepted"] == 3
        assert result["rejected"] == 0
        assert result["errors"] is None
        assert mock_send.call_count == 3

    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_empty_serial_number(self, mock_db, mock_send):
        mock_db.return_value = []
        devices = [{"serialNumber": "", "udid": "UD1"}, _device("SN2", "UD2")]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["accepted"] == 1
        assert result["rejected"] == 1
        assert result["errors"][0]["index"] == 0
        assert "empty" in result["errors"][0]["reason"].lower()
        assert mock_send.call_count == 1

    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_empty_udid(self, mock_db, mock_send):
        mock_db.return_value = []
        devices = [{"serialNumber": "SN1", "udid": "  "}, _device("SN2", "UD2")]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["accepted"] == 1
        assert result["rejected"] == 1
        assert "udid" in result["errors"][0]["reason"].lower()

    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_intra_batch_duplicate_serial(self, mock_db, mock_send):
        """2 devices with same serial → first accepted, second rejected."""
        mock_db.return_value = []
        devices = [_device("SN1", "UD1"), _device("SN1", "UD2")]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["accepted"] == 1
        assert result["rejected"] == 1
        assert result["errors"][0]["index"] == 1
        assert "Duplicate serialNumber" in result["errors"][0]["reason"]
        assert mock_send.call_count == 1

    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_intra_batch_duplicate_udid(self, mock_db, mock_send):
        """2 devices with same udid → first accepted, second rejected."""
        mock_db.return_value = []
        devices = [_device("SN1", "UD1"), _device("SN2", "UD1")]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["accepted"] == 1
        assert result["rejected"] == 1
        assert "Duplicate udid" in result["errors"][0]["reason"]

    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_db_duplicate_serial(self, mock_db, mock_send):
        """Serial already in DB → rejected."""
        mock_db.return_value = [{"serial_number": "SN1", "udid": "EXISTING_UD"}]
        devices = [_device("SN1", "UD_NEW"), _device("SN2", "UD2")]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["accepted"] == 1
        assert result["rejected"] == 1
        assert "already exists" in result["errors"][0]["reason"]
        assert mock_send.call_count == 1

    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_db_duplicate_udid(self, mock_db, mock_send):
        """UDID already in DB → rejected."""
        mock_db.return_value = [{"serial_number": "EXISTING_SN", "udid": "UD1"}]
        devices = [_device("SN_NEW", "UD1"), _device("SN2", "UD2")]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["accepted"] == 1
        assert result["rejected"] == 1
        assert "udid already exists" in result["errors"][0]["reason"]

    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_mixed_batch(self, mock_db, mock_send):
        """5 devices: 2 valid + 1 empty + 1 batch-dup + 1 DB-dup."""
        mock_db.return_value = [{"serial_number": "SN5", "udid": "UD5_OLD"}]
        devices = [
            _device("SN1", "UD1"),              # valid
            {"serialNumber": "", "udid": "UD2"},  # empty serial
            _device("SN1", "UD3"),              # batch-dup serial (SN1)
            _device("SN4", "UD4"),              # valid
            _device("SN5", "UD5"),              # DB-dup serial
        ]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["totalRequested"] == 5
        assert result["accepted"] == 2
        assert result["rejected"] == 3
        assert len(result["errors"]) == 3
        # Errors sorted by index
        assert result["errors"][0]["index"] == 1
        assert result["errors"][1]["index"] == 2
        assert result["errors"][2]["index"] == 4
        assert mock_send.call_count == 2

    @patch("handler.send_message")
    @patch.object(DBConnection, "find_existing_identifiers")
    def test_all_rejected(self, mock_db, mock_send):
        """All devices fail → accepted=0, SQS never called."""
        mock_db.return_value = []
        devices = [
            {"serialNumber": "", "udid": "UD1"},
            {"serialNumber": "SN2", "udid": ""},
        ]
        event = _make_appsync_event("uploadDevices", {"devices": devices})
        result = app.resolve(event, MagicMock())

        assert result["accepted"] == 0
        assert result["rejected"] == 2
        mock_send.assert_not_called()
