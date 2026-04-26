"""Permission codes for action_resolver.

Must match rows seeded by the permission catalog migration into
``accesscontrol.permissions`` (seeded in P0 of GH-35).

Codes:
  action:execute   — assignAction, assignBulkAction (P1a)
  actionlog:read   — getActionLog, listActionLogs, generateActionLogErrorReport (P1b)
"""

from __future__ import annotations

PERM_ACTION_EXECUTE = "action:execute"
PERM_ACTIONLOG_READ = "actionlog:read"
