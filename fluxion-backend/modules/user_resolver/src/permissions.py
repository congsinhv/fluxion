"""Permission codes for user_resolver.

Must match rows seeded by the permission catalog migration
(`a1b2c3d4e5f6_seed_permission_catalog.py`) into `accesscontrol.permissions`.
"""

from __future__ import annotations

PERM_USER_SELF = "user:self"
PERM_USER_READ = "user:read"
PERM_USER_ADMIN = "user:admin"
