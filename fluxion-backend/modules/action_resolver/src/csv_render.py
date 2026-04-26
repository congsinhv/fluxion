"""CSV renderer for ActionLog error reports.

Produces UTF-8 + BOM encoded bytes suitable for S3 upload and Excel/LibreOffice
opening without charset prompts.

Columns (fixed order):
  device_id, error_code, error_message, finished_at

0-row case: returns header-only CSV (with BOM) — callers must NOT raise on empty.
"""

from __future__ import annotations

import csv
import io
from typing import Any

# Fixed column order matches schema.graphql comment + GH-35 architectural decision #8.
_HEADERS: list[str] = ["device_id", "error_code", "error_message", "finished_at"]


def render_failed_devices_csv(rows: list[dict[str, Any]]) -> bytes:
    """Render a list of failed-device dicts to UTF-8 + BOM CSV bytes.

    Each dict in ``rows`` must contain keys: ``device_id``, ``error_code``,
    ``error_message``, ``finished_at``.  Missing keys are written as empty
    strings (defensive).

    Args:
        rows: List of failed-device row dicts from db.get_failed_devices_for_batch.
              May be empty — produces header-only CSV with BOM.

    Returns:
        UTF-8 + BOM encoded bytes (starts with ``\\xef\\xbb\\xbf``).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_HEADERS)
    for row in rows:
        writer.writerow(
            [
                str(row.get("device_id", "")),
                str(row.get("error_code", "")),
                str(row.get("error_message", "")),
                str(row.get("finished_at", "")),
            ]
        )
    return buf.getvalue().encode("utf-8-sig")
