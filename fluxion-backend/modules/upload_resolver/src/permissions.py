"""Permission codes for upload_resolver.

Must match rows seeded by the permission catalog migration into
``accesscontrol.permissions`` (seeded in P0 of GH-35).

Codes:
  upload:write   — uploadDevices (P2)
"""

from __future__ import annotations

PERM_UPLOAD_WRITE = "upload:write"
