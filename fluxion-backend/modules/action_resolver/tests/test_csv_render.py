"""Tests for csv_render.render_failed_devices_csv."""

from __future__ import annotations

import csv
import io

from csv_render import render_failed_devices_csv

_BOM = b"\xef\xbb\xbf"
_EXPECTED_HEADER = "device_id,error_code,error_message,finished_at"


def _parse_csv(data: bytes) -> list[list[str]]:
    """Strip BOM and parse CSV bytes to list of row lists."""
    text = data.decode("utf-8-sig")  # utf-8-sig strips BOM on decode
    reader = csv.reader(io.StringIO(text))
    return list(reader)


class TestRenderFailedDevicesCsv:
    def test_bom_present(self) -> None:
        result = render_failed_devices_csv([])
        assert result.startswith(_BOM), "CSV must start with UTF-8 BOM (0xEF 0xBB 0xBF)"

    def test_header_only_on_empty_rows(self) -> None:
        result = render_failed_devices_csv([])
        rows = _parse_csv(result)
        assert rows == [["device_id", "error_code", "error_message", "finished_at"]]

    def test_header_columns_correct_order(self) -> None:
        result = render_failed_devices_csv([])
        # raw text after BOM
        text = result.decode("utf-8-sig")
        first_line = text.split("\n")[0]
        assert first_line == _EXPECTED_HEADER

    def test_single_row(self) -> None:
        rows = [
            {
                "device_id": "dev-001",
                "error_code": "TIMEOUT",
                "error_message": "device timed out",
                "finished_at": "2026-04-26T10:00:00+00:00",
            }
        ]
        result = render_failed_devices_csv(rows)
        parsed = _parse_csv(result)
        assert len(parsed) == 2  # header + 1 data row
        assert parsed[1] == ["dev-001", "TIMEOUT", "device timed out", "2026-04-26T10:00:00+00:00"]

    def test_multiple_rows(self) -> None:
        rows = [
            {
                "device_id": f"dev-{i}",
                "error_code": "ERR",
                "error_message": f"error {i}",
                "finished_at": "2026-01-01T00:00:00+00:00",
            }
            for i in range(5)
        ]
        result = render_failed_devices_csv(rows)
        parsed = _parse_csv(result)
        assert len(parsed) == 6  # header + 5 rows
        assert parsed[0] == ["device_id", "error_code", "error_message", "finished_at"]
        assert parsed[1][0] == "dev-0"
        assert parsed[5][0] == "dev-4"

    def test_missing_keys_become_empty_string(self) -> None:
        """Defensive: partial dicts should not raise."""
        rows = [{"device_id": "dev-x"}]
        result = render_failed_devices_csv(rows)
        parsed = _parse_csv(result)
        assert parsed[1] == ["dev-x", "", "", ""]

    def test_returns_bytes(self) -> None:
        result = render_failed_devices_csv([])
        assert isinstance(result, bytes)

    def test_newline_terminator(self) -> None:
        """Lines must end with \\n not \\r\\n."""
        result = render_failed_devices_csv([])
        assert b"\r\n" not in result

    def test_excel_round_trip(self) -> None:
        """Simulate Excel opening: decode with utf-8-sig strips BOM cleanly."""
        rows = [
            {
                "device_id": "abc",
                "error_code": "CODE",
                "error_message": "msg with, comma",
                "finished_at": "2026-04-26T00:00:00Z",
            }
        ]
        result = render_failed_devices_csv(rows)
        text = result.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        parsed = list(reader)
        # comma in message_content must be quoted by csv.writer
        assert parsed[1][2] == "msg with, comma"
