"""Event key constants and magic strings used in this Lambda.

Centralising them here prevents typo-driven KeyError bugs and makes
grep-ability straightforward when tracing event shapes.
"""

from __future__ import annotations

# AppSync resolver event keys
KEY_ARGUMENTS: str = "arguments"
KEY_IDENTITY: str = "identity"
KEY_FIELD: str = "info"

# SQS event key
KEY_RECORDS: str = "Records"
