"""Auth helpers: context extraction + permission decorator for device_resolver.

Identical pattern to _template/src/auth.py — copied per design-patterns.md §1
(no shared lib across Lambda boundaries).
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from config import logger
from db import Database
from exceptions import AuthenticationError, ForbiddenError, InvalidInputError

F = TypeVar("F", bound=Callable[..., Any])
M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class Context:
    """Resolved caller context, populated once per Lambda invocation."""

    cognito_sub: str
    user_id: int
    tenant_id: int
    tenant_schema: str


def build_context_from(event: dict[str, Any]) -> Context:
    """Extract and resolve caller identity from an AppSync resolver event."""
    try:
        claims: dict[str, Any] = event["identity"]["claims"]
        cognito_sub: str = claims["sub"]
        raw_tenant_id: str = claims["custom:tenant_id"]
    except (KeyError, TypeError) as exc:
        raise AuthenticationError("missing identity claims") from exc

    try:
        tenant_id = int(raw_tenant_id)
    except (ValueError, TypeError) as exc:
        raise InvalidInputError(f"custom:tenant_id is not an integer: {raw_tenant_id!r}") from exc

    with Database() as db:
        tenant_schema = db.get_schema_name(tenant_id)
        user_id = _resolve_user_id(db, cognito_sub)

    return Context(
        cognito_sub=cognito_sub,
        user_id=user_id,
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
    )


def permission_required(permission: str) -> Callable[[F], F]:
    """Decorator: resolve caller context and enforce a permission code.

    Wraps a field handler ``(args, event, correlation_id) -> Any``.
    Injects resolved ``Context`` as third positional arg to the wrapped fn.
    The wrapped fn signature becomes ``(args, ctx, correlation_id)``.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(
            args: dict[str, Any],
            event: dict[str, Any],
            correlation_id: str,
        ) -> Any:
            ctx = build_context_from(event)
            with Database() as db:
                if not db.has_permission(ctx.cognito_sub, ctx.tenant_id, permission):
                    logger.warning(
                        "auth.permission_denied",
                        extra={
                            "permission": permission,
                            "cognito_sub": ctx.cognito_sub,
                            "tenant_id": ctx.tenant_id,
                            "correlation_id": correlation_id,
                        },
                    )
                    raise ForbiddenError(f"missing permission: {permission}")
            return fn(args, ctx, correlation_id)

        return wrapper  # type: ignore[return-value]

    return decorator


def validate_input(model: type[M], key: str | None = None) -> Callable[[F], F]:  # noqa: UP047
    """Decorator: validate an input dict against a Pydantic model.

    The validated instance is appended as the last positional arg to the wrapped fn.
    Wrapped signature: ``(args, ctx, correlation_id, inp)``.

    Args:
        model: Pydantic model class to validate against.
        key: If set, validate ``args[key]`` (default empty dict if missing) instead
            of ``args``. Use ``key="input"`` for AppSync mutation handlers.

    Raises:
        InvalidInputError: Validation failed.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(
            args: dict[str, Any],
            ctx: Context,
            correlation_id: str,
        ) -> Any:
            raw: Any = args if key is None else args.get(key, {})
            try:
                inp = model.model_validate(raw)
            except Exception as exc:
                raise InvalidInputError(str(exc)) from exc
            return fn(args, ctx, correlation_id, inp)

        return wrapper  # type: ignore[return-value]

    return decorator


def _resolve_user_id(db: Database, cognito_sub: str) -> int:
    """Fetch accesscontrol.users.id for a cognito_sub."""
    from exceptions import DatabaseError  # local import avoids circular at module level

    conn = db._require_conn()  # noqa: SLF001
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM accesscontrol.users WHERE cognito_sub = %s",
                (cognito_sub,),
            )
            row = cur.fetchone()
    except Exception as exc:
        raise DatabaseError("user lookup failed") from exc

    if not row:
        raise AuthenticationError(f"no user for cognito_sub={cognito_sub!r}")

    return int(row["id"])
