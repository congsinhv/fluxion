"""Permission codes for platform_resolver.

Must match rows seeded by the permission catalog migration
(`a1b2c3d4e5f6_seed_permission_catalog.py`) into `accesscontrol.permissions`.
"""

from __future__ import annotations

PERM_PLATFORM_READ = "platform:read"
PERM_PLATFORM_ADMIN = "platform:admin"
