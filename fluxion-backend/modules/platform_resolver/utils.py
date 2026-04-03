"""Response formatting utilities for platform_resolver."""

import json
import re


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format (alphanumeric + underscore only)."""
    if not re.match(r"^[a-zA-Z0-9_]+$", tenant_id):
        raise ValueError(f"Invalid tenant_id format: {tenant_id}")
    return tenant_id


def format_state(row: dict) -> dict:
    return {"id": row["id"], "name": row["name"]}


def format_policy(row: dict) -> dict:
    policy = {
        "id": row["id"],
        "name": row["name"],
        "stateId": row["state_id"],
        "serviceTypeId": row["service_type_id"],
        "color": row.get("color"),
    }
    # Include nested state if JOINed (state_name comes from JOIN)
    if row.get("state_name"):
        policy["state"] = {"id": row["state_id"], "name": row["state_name"]}
    return policy


def format_action(row: dict) -> dict:
    action = {
        "id": str(row["id"]),
        "name": row["name"],
        "actionTypeId": row["action_type_id"],
        "fromStateId": row.get("from_state_id"),
        "serviceTypeId": row.get("service_type_id"),
        "applyPolicyId": row["apply_policy_id"],
        "configuration": json.dumps(row["configuration"]) if row.get("configuration") else None,
    }
    if row.get("policy_name"):
        action["applyPolicy"] = {
            "id": row["apply_policy_id"],
            "name": row["policy_name"],
            "stateId": row["policy_state_id"],
            "color": row.get("policy_color"),
        }
    return action


def format_service(row: dict) -> dict:
    return {"id": row["id"], "name": row["name"], "isEnabled": row["is_enabled"]}
