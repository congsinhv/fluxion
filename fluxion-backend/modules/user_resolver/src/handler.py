"""Lambda handler for user_resolver — me, getUser, listUsers, createUser, updateUser."""

import os

import boto3
from aws_lambda_powertools.event_handler import AppSyncResolver
from aws_lambda_powertools.utilities.typing import LambdaContext
from config import logger, tracer
from const import DEFAULT_LIMIT, MAX_LIMIT
from db import DBConnection
from exceptions import (
    FluxionError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from utils import (
    decode_next_token,
    encode_next_token,
    format_user,
    get_tenant,
    require_admin,
)

app = AppSyncResolver()

COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
cognito_client = boto3.client("cognito-idp")


# ─── Queries ─────────────────────────────────────────────────────────────────────


@app.resolver(type_name="Query", field_name="me")
def me() -> dict:
    tenant = get_tenant(app)
    try:
        cognito_sub = app.current_event.identity.sub
        row = DBConnection.get_user_by_cognito_sub(schema_name=tenant, cognito_sub=cognito_sub)
        if not row:
            raise UserNotFoundError(cognito_sub)
        return format_user(row)
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in me")
        raise


@app.resolver(type_name="Query", field_name="getUser")
def get_user(id: str) -> dict:
    tenant = get_tenant(app)
    try:
        row = DBConnection.get_user_by_id(schema_name=tenant, user_id=id)
        if not row:
            raise UserNotFoundError(id)
        return format_user(row)
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in getUser")
        raise


@app.resolver(type_name="Query", field_name="listUsers")
def list_users(limit: int = DEFAULT_LIMIT, nextToken: str | None = None) -> dict:  # noqa: N803
    tenant = get_tenant(app)
    limit = min(limit, MAX_LIMIT)
    try:
        offset = decode_next_token(nextToken)
        rows = DBConnection.list_users(schema_name=tenant, limit=limit, offset=offset)

        has_more = len(rows) > limit
        items = [format_user(r) for r in rows[:limit]]
        new_token = encode_next_token(offset + limit) if has_more else None
        total_count = DBConnection.count_users(schema_name=tenant)

        return {"items": items, "nextToken": new_token, "totalCount": total_count}
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in listUsers")
        raise


# ─── Mutations (ADMIN only) ─────────────────────────────────────────────────────


@app.resolver(type_name="Mutation", field_name="createUser")
def create_user(input: dict) -> dict:
    require_admin(app)
    tenant = get_tenant(app)
    cognito_sub = None
    try:
        email = input["email"]
        name = input["name"]
        role = input["role"]

        # Step 1: Create Cognito user
        cognito_response = cognito_client.admin_create_user(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:role", "Value": role},
                {"Name": "custom:tenant_id", "Value": tenant},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
        # Extract UUID sub from Cognito attributes (Username is email, not sub)
        attrs = {a["Name"]: a["Value"] for a in cognito_response["User"]["Attributes"]}
        cognito_sub = attrs["sub"]

        # Step 2: Create DB record
        row = DBConnection.create_user(
            schema_name=tenant,
            email=email,
            name=name,
            role=role,
            cognito_sub=cognito_sub,
        )
        return format_user(row)

    except cognito_client.exceptions.UsernameExistsException:
        raise UserAlreadyExistsError(input["email"])
    except FluxionError:
        raise
    except Exception:
        # Rollback: delete Cognito user if DB insert failed
        if cognito_sub:
            try:
                cognito_client.admin_delete_user(
                    UserPoolId=COGNITO_USER_POOL_ID, Username=cognito_sub
                )
                logger.info(f"Rolled back Cognito user {cognito_sub}")
            except Exception:
                logger.exception(f"Failed to rollback Cognito user {cognito_sub}")
        logger.exception("Unexpected error in createUser")
        raise


@app.resolver(type_name="Mutation", field_name="updateUser")
def update_user(id: str, input: dict) -> dict:
    require_admin(app)
    tenant = get_tenant(app)
    try:
        row = DBConnection.update_user(schema_name=tenant, user_id=id, input_data=input)
        if not row:
            raise UserNotFoundError(id)

        # Sync role to Cognito if changed
        if input.get("role") and row.get("cognito_sub"):
            try:
                cognito_client.admin_update_user_attributes(
                    UserPoolId=COGNITO_USER_POOL_ID,
                    Username=row["cognito_sub"],
                    UserAttributes=[{"Name": "custom:role", "Value": input["role"]}],
                )
            except Exception:
                logger.exception("Failed to sync role to Cognito")

        return format_user(row)
    except FluxionError:
        raise
    except Exception:
        logger.exception("Unexpected error in updateUser")
        raise


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda entry point — dispatches to AppSyncResolver."""
    logger.debug("Event received", extra={"event": event})
    return app.resolve(event, context)
