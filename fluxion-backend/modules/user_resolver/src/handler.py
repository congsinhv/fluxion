"""Lambda entry point — AppSync field dispatch for user_resolver.

Fields handled:
  getCurrentUser()                              → User!
  getUser(id: ID!)                              → User
  listUsers(limit: Int, nextToken: String)      → UserConnection!
  createUser(input: CreateUserInput!)           → User!
  updateUser(id: ID!, input: UpdateUserInput!)  → User!
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

import cognito
from auth import Context, permission_required
from config import DATABASE_URI, POWERTOOLS_SERVICE_NAME
from db import Database, _decode_cursor, _encode_cursor
from exceptions import FluxionError, InvalidInputError, NotFoundError, UnknownFieldError
from schema_types import (
    CreateUserInput,
    ListUsersInput,
    UpdateUserInput,
    UserConnectionResponse,
    UserResponse,
)

logger = logging.getLogger(POWERTOOLS_SERVICE_NAME)


# ---------------------------------------------------------------------------
# DB row + Cognito attrs → UserResponse
# ---------------------------------------------------------------------------

def _build_user_response(row: dict[str, Any], cognito_attrs: dict[str, str]) -> dict[str, Any]:
    """Merge DB row and Cognito attributes into a UserResponse dict."""
    created_at = str(row["created_at"])
    return UserResponse(
        id=str(row["id"]),
        email=row["email"],
        name=row["name"] or "",
        role=cognito_attrs.get("custom:role", "OPERATOR"),
        isActive=bool(row["enabled"]),
        createdAt=created_at,
        updatedAt=created_at,  # no updated_at column in v1 (tech debt)
    ).model_dump()


# ---------------------------------------------------------------------------
# Field handlers
# ---------------------------------------------------------------------------

@permission_required("user:self")
def get_current_user(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    with Database(dsn=DATABASE_URI) as db:
        row = db.get_user_by_cognito_sub(ctx.cognito_sub)
    cog_attrs = cognito.admin_get_user(row["email"])
    return _build_user_response(row, cog_attrs)


@permission_required("user:read")
def get_user(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        user_id = int(args["id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidInputError("getUser: id must be a valid integer") from exc
    with Database(dsn=DATABASE_URI) as db:
        row = db.get_user_by_id(user_id)
    cog_attrs = cognito.admin_get_user(row["email"])
    return _build_user_response(row, cog_attrs)


@permission_required("user:read")
def list_users(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        inp = ListUsersInput.model_validate(args)
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc

    after_id: int | None = None
    if inp.nextToken:
        after_id = _decode_cursor(inp.nextToken)

    with Database(dsn=DATABASE_URI) as db:
        rows = db.list_users(limit=inp.limit, after_id=after_id)

    # Enrich each row with Cognito role — N+1 acceptable for admin-only paginated view.
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            cog_attrs = cognito.admin_get_user(row["email"])
        except NotFoundError:
            cog_attrs = {}
        items.append(_build_user_response(row, cog_attrs))

    next_token: str | None = None
    if len(rows) == inp.limit:
        next_token = _encode_cursor(int(rows[-1]["id"]))

    return UserConnectionResponse(
        items=[UserResponse(**i) for i in items],
        nextToken=next_token,
        totalCount=None,  # totalCount omitted in v1 (requires COUNT(*) query)
    ).model_dump()


@permission_required("user:admin")
def create_user(args: dict[str, Any], ctx: Context, cid: str) -> dict[str, Any]:
    try:
        inp = CreateUserInput.model_validate(args.get("input", {}))
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc

    temp_password = secrets.token_urlsafe(16)

    # Step 1 — DB placeholder (cognito_sub=NULL)
    with Database(dsn=DATABASE_URI) as db:
        user_id = db.create_user_placeholder(email=inp.email, name=inp.name)

    # Steps 2-3 — Cognito; rollback DB on any failure
    try:
        sub = cognito.admin_create_user(email=inp.email, temp_password=temp_password)
        cognito.admin_update_user_attributes(
            username=inp.email,
            attrs={"custom:role": inp.role},
        )
    except Exception:
        logger.warning(
            "create_user.cognito_failed_rolling_back",
            extra={"user_id": user_id, "correlation_id": cid},
        )
        with Database(dsn=DATABASE_URI) as db:
            db.delete_user(user_id)
        raise

    # Step 4 — bind sub to DB row
    with Database(dsn=DATABASE_URI) as db:
        db.set_user_cognito_sub(user_id, sub)
        row = db.get_user_by_id(user_id)

    return _build_user_response(row, {"custom:role": inp.role, "sub": sub})


@permission_required("user:admin")
def update_user(args: dict[str, Any], ctx: Context, _cid: str) -> dict[str, Any]:
    try:
        user_id = int(args["id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidInputError("updateUser: id must be a valid integer") from exc
    try:
        inp = UpdateUserInput.model_validate(args.get("input", {}))
    except Exception as exc:
        raise InvalidInputError(str(exc)) from exc

    patch = inp.model_dump(exclude_unset=True)
    if not patch:
        raise InvalidInputError("updateUser: at least one field must be provided")

    new_role: str | None = patch.pop("role", None)

    if patch:
        # DB update (name, isActive columns)
        with Database(dsn=DATABASE_URI) as db:
            row = db.update_user(user_id, patch)
        email = row["email"]
    else:
        # role-only patch — fetch current row for the Cognito username
        with Database(dsn=DATABASE_URI) as db:
            row = db.get_user_by_id(user_id)
        email = row["email"]

    if new_role:
        cognito.admin_update_user_attributes(username=email, attrs={"custom:role": new_role})

    cog_attrs = cognito.admin_get_user(email)
    return _build_user_response(row, cog_attrs)


# ---------------------------------------------------------------------------
# Dispatch table + entry point
# ---------------------------------------------------------------------------

FIELD_HANDLERS = {
    "getCurrentUser": get_current_user,
    "getUser": get_user,
    "listUsers": list_users,
    "createUser": create_user,
    "updateUser": update_user,
}


def lambda_handler(event: dict[str, Any], context: Any) -> Any:
    """AppSync Lambda direct resolver entry point."""
    correlation_id: str = getattr(context, "aws_request_id", "local")
    field: str = event.get("info", {}).get("fieldName", "")

    logger.info("resolver.invoked", extra={"field": field, "correlation_id": correlation_id})

    try:
        handler = FIELD_HANDLERS.get(field)
        if handler is None:
            raise UnknownFieldError(f"no handler for field: {field!r}")
        return handler(event.get("arguments", {}), event, correlation_id)
    except FluxionError as exc:
        logger.warning(
            "resolver.error",
            extra={"field": field, "error_type": exc.code, "correlation_id": correlation_id},
        )
        return exc.to_appsync_error()
