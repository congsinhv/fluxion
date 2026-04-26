"""Auth helpers: context extraction + permission decorator.

Two public symbols:
  - ``build_context_from(event)`` — parses Cognito claims into a ``Context``.
  - ``permission_required(permission)`` — decorator that enforces a permission code.
  - ``validate_input(model, key)`` — decorator that validates args against a Pydantic model.

Design-patterns.md §11.2: tenant_schema is resolved from the validated
Cognito ``custom:tenant_id`` claim via accesscontrol.tenants lookup.
``cognito_sub`` comes from ``event["identity"]["claims"]["sub"]`` which
AppSync already verified — no re-verification needed.
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
    """Resolved caller context, populated once per Lambda invocation.

    Attributes:
        cognito_sub: Cognito user subject UUID (from JWT claim ``sub``).
        user_id: ``accesscontrol.users.id`` for this subject.
        tenant_id: ``accesscontrol.tenants.id`` (BIGINT) from Cognito claim.
        tenant_schema: Validated bare schema name (e.g. ``"dev1"``).
    """

    cognito_sub: str
    user_id: int
    tenant_id: int
    tenant_schema: str


def build_context_from(event: dict[str, Any]) -> Context:
    """Extract and resolve caller identity from an AppSync resolver event.

    Flow (per design-patterns.md §11.2):
    1. Read ``cognito_sub`` from ``event["identity"]["claims"]["sub"]``.
    2. Read ``tenant_id`` (BIGINT) from ``event["identity"]["claims"]["custom:tenant_id"]``.
    3. Look up ``accesscontrol.users`` to get ``user_id``.
    4. Look up ``accesscontrol.tenants`` to get validated ``schema_name``.

    Args:
        event: Raw AppSync Lambda resolver event.

    Returns:
        Populated ``Context`` for this invocation.

    Raises:
        AuthenticationError: Claims missing or identity block absent.
        InvalidInputError: ``custom:tenant_id`` claim is not a valid integer.
    """
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

    Wraps a field handler ``(args, ctx, correlation_id) -> Any``.
    Injects the resolved ``Context`` as ``ctx`` — the wrapped function
    does NOT need to call ``build_context_from`` itself.

    Args:
        permission: Permission code to enforce (e.g. ``"action:execute"``).

    Returns:
        Decorator that injects ``ctx`` and raises ``ForbiddenError`` on miss.

    Raises:
        ForbiddenError: User does not hold the permission for the tenant.
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


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _resolve_user_id(db: Database, cognito_sub: str) -> int:
    """Fetch accesscontrol.users.id for a cognito_sub.

    Args:
        db: Open Database instance (inside context manager).
        cognito_sub: Cognito subject claim.

    Returns:
        Integer ``accesscontrol.users.id``.

    Raises:
        AuthenticationError: No user row found for this cognito_sub.
    """
    from exceptions import DatabaseError  # local import avoids circular at module level

    conn = db._require_conn()  # noqa: SLF001 — auth.py is a sibling module, not external
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
