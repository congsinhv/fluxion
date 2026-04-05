"""Pagination and response formatting utilities for device_resolver."""

import base64
import json
import re

from config import logger


def decode_next_token(next_token: str | None) -> int:
    """Decode base64 nextToken to offset. Returns 0 if None/invalid."""
    if not next_token:
        return 0
    try:
        decoded = json.loads(base64.b64decode(next_token))
        return decoded.get("offset", 0)
    except Exception:
        logger.warning(f"Invalid nextToken: {next_token}")
        return 0


def encode_next_token(offset: int) -> str:
    """Encode offset to base64 nextToken."""
    return base64.b64encode(json.dumps({"offset": offset}).encode()).decode()


def validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id format (alphanumeric + underscore only) to prevent SQL injection."""
    if not re.match(r"^[a-zA-Z0-9_]+$", tenant_id):
        raise ValueError(f"Invalid tenant_id format: {tenant_id}")
    return tenant_id


def format_device(row: dict) -> dict:
    """Format a device row with nested state, policy, information, tokens."""
    device = {
        "id": str(row["id"]),
        "stateId": row["state_id"],
        "currentPolicyId": row.get("current_policy_id"),
        "assignedActionId": str(row["assigned_action_id"]) if row.get("assigned_action_id") else None,
        "createdAt": row["created_at"].isoformat(),
        "updatedAt": row["updated_at"].isoformat(),
        "state": {"id": row["state_id"], "name": row["state_name"]},
    }
    # Nested policy (nullable — check via current_policy_id from base table)
    if row.get("current_policy_id"):
        device["currentPolicy"] = {
            "id": row["current_policy_id"],
            "name": row["policy_name"],
            "stateId": row["policy_state_id"],
            "serviceTypeId": row["policy_service_type_id"],
            "color": row.get("policy_color"),
        }
    # Nested information (nullable — check via serial_number from JOIN)
    if row.get("serial_number"):
        device["information"] = {
            "id": str(row.get("info_id", "")),
            "deviceId": str(row["id"]),
            "serialNumber": row["serial_number"],
            "udid": row.get("udid"),
            "name": row.get("device_name"),
            "model": row.get("model"),
            "osVersion": row.get("os_version"),
            "batteryLevel": row.get("battery_level"),
            "wifiMac": row.get("wifi_mac"),
            "isSupervised": row.get("is_supervised"),
            "lastCheckinAt": row["last_checkin_at"].isoformat() if row.get("last_checkin_at") else None,
            "extFields": row.get("info_ext_fields"),
        }
    # Nested tokens (nullable)
    if row.get("token_id"):
        device["tokens"] = {
            "id": str(row["token_id"]),
            "deviceId": str(row["id"]),
            "topic": row["topic"],
            "updatedAt": row["token_updated_at"].isoformat() if row.get("token_updated_at") else None,
        }
    return device


def format_device_list_item(row: dict) -> dict:
    """Format a device row for list view (lighter than full device)."""
    return {
        "id": str(row["id"]),
        "stateId": row["state_id"],
        "currentPolicyId": row.get("current_policy_id"),
        "assignedActionId": str(row["assigned_action_id"]) if row.get("assigned_action_id") else None,
        "createdAt": row["created_at"].isoformat(),
        "updatedAt": row["updated_at"].isoformat(),
        "state": {"id": row["state_id"], "name": row["state_name"]},
        "information": {
            "serialNumber": row.get("serial_number"),
            "name": row.get("device_name"),
            "model": row.get("model"),
        } if row.get("serial_number") else None,
    }


def format_milestone(row: dict) -> dict:
    """Format a milestone row with nested action and policy."""
    milestone = {
        "id": str(row["id"]),
        "deviceId": str(row["device_id"]),
        "assignedActionId": str(row["assigned_action_id"]) if row.get("assigned_action_id") else None,
        "policyId": row.get("policy_id"),
        "createdAt": row["created_at"].isoformat(),
        "extFields": row.get("ext_fields"),
    }
    if row.get("assigned_action_id"):
        milestone["action"] = {
            "id": str(row["assigned_action_id"]),
            "name": row["action_name"],
            "actionTypeId": row["action_type_id"],
        }
    if row.get("policy_id"):
        milestone["policy"] = {
            "id": row["policy_id"],
            "name": row["policy_name"],
            "stateId": row["policy_state_id"],
            "color": row.get("policy_color"),
        }
    return milestone


def format_action(row: dict) -> dict:
    """Format an action row with nested applyPolicy."""
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
