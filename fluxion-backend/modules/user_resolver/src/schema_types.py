"""Pydantic v2 DTOs for user_resolver — shaped to match schema.graphql exactly.

AppSync receives whatever model_dump() emits, so field names MUST match GraphQL
type field names (camelCase).

GraphQL types handled:
  type User {
    id: ID!, email: String!, name: String!, role: UserRole!,
    isActive: Boolean!, createdAt: AWSDateTime!, updatedAt: AWSDateTime!
  }
  type UserConnection { items: [User!]!, nextToken: String, totalCount: Int }

Queries:
  getCurrentUser: User!
  getUser(id: ID!): User
  listUsers(limit: Int = 20, nextToken: String): UserConnection!

Mutations:
  createUser(input: CreateUserInput!): User!
  updateUser(id: ID!, input: UpdateUserInput!): User!

Table: accesscontrol.users (id, email, cognito_sub, name, enabled, created_at)
  - role       → Cognito custom:role attribute (fetched via admin_get_user)
  - isActive   → DB enabled column
  - updatedAt  → DB created_at (no updated_at column in v1; tracked as tech debt)

UserRole enum: ADMIN | OPERATOR (matches schema.graphql)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseInput(BaseModel):
    """Strict input base — unknown fields rejected immediately."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BaseResponse(BaseModel):
    """Permissive response base — forward-compatible with new server fields."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Response types — match GraphQL User / UserConnection field names
# ---------------------------------------------------------------------------


class UserResponse(BaseResponse):
    """Maps accesscontrol.users + Cognito role → GraphQL User type.

    id is BIGINT in DB, serialised as str to match GraphQL ID scalar.
    updatedAt mirrors createdAt until an updated_at column is added (v2 TODO).
    """

    id: str           # BIGINT → GraphQL ID
    email: str
    name: str
    role: str         # Cognito custom:role (ADMIN | OPERATOR)
    isActive: bool    # DB enabled
    createdAt: str    # DB created_at (ISO-8601 string)
    updatedAt: str    # mirrors createdAt — no updated_at column in v1

    @classmethod
    def from_row(cls, row: dict[str, Any], cognito_attrs: dict[str, str]) -> UserResponse:
        """Build response from a DB row plus Cognito user attributes."""
        created_at = str(row["created_at"])
        return cls(
            id=str(row["id"]),
            email=row["email"],
            name=row["name"] or "",
            role=cognito_attrs.get("custom:role", "OPERATOR"),
            isActive=bool(row["enabled"]),
            createdAt=created_at,
            updatedAt=created_at,  # no updated_at column in v1 (tech debt)
        )

    @classmethod
    def dump_row(cls, row: dict[str, Any], cognito_attrs: dict[str, str]) -> dict[str, Any]:
        return cls.from_row(row, cognito_attrs).model_dump()


class UserConnectionResponse(BaseResponse):
    """Maps paginated user list → GraphQL UserConnection type."""

    items: list[UserResponse]
    nextToken: str | None = None
    totalCount: int | None = None


# ---------------------------------------------------------------------------
# Query input models
# ---------------------------------------------------------------------------


class ListUsersInput(BaseInput):
    """Arguments for listUsers(limit: Int = 20, nextToken: String)."""

    limit: int = Field(default=20, ge=1, le=100)
    nextToken: str | None = None


# ---------------------------------------------------------------------------
# Mutation input models
# ---------------------------------------------------------------------------


class CreateUserInput(BaseInput):
    """Input for createUser — all fields required per schema."""

    email: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    role: str = Field(..., pattern="^(ADMIN|OPERATOR)$")


class UpdateUserInput(BaseInput):
    """Input for updateUser — all fields optional (PATCH semantics, exclude_unset)."""

    name: str | None = None
    role: str | None = Field(default=None, pattern="^(ADMIN|OPERATOR)$")
    isActive: bool | None = None
