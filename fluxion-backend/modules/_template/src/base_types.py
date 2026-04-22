"""Pydantic v2 base models and shared types for Lambda resolvers.

All resolver DTOs inherit from ``BaseInput`` / ``BaseResponse``.
``extra="forbid"`` on every model: unknown fields from a misconfigured
client are rejected, not silently dropped (see design-patterns.md §7).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BaseInput(BaseModel):
    """Base class for all resolver input models.

    Enforces ``extra="forbid"`` so version drift from clients surfaces
    immediately rather than silently accepting unknown fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class BaseResponse(BaseModel):
    """Base class for all resolver response models.

    Allows extra fields on responses so forward-compatible additions
    (new fields added server-side) do not break existing consumers.
    """

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Shared pagination types (copy-paste per Lambda; no shared lib)
# ---------------------------------------------------------------------------


class PaginationInput(BaseInput):
    """Cursor-based pagination arguments for list fields.

    Attributes:
        first: Maximum number of items to return (1–100).
        after: Opaque cursor from a previous page's ``end_cursor``.
    """

    first: int = Field(default=20, ge=1, le=100)
    after: str | None = Field(default=None)


class PageInfo(BaseResponse):
    """Relay-style page info returned with every connection response.

    Attributes:
        has_next_page: True when more items exist after ``end_cursor``.
        end_cursor: Opaque cursor pointing to the last item in this page.
    """

    has_next_page: bool
    end_cursor: str | None = None


class ConnectionResponse[T](BaseResponse):
    """Generic Relay-style connection wrapper.

    Example usage::

        class DeviceConnection(ConnectionResponse[DeviceOutput]):
            pass

    Attributes:
        items: List of edge nodes for this page.
        page_info: Pagination metadata.
        total_count: Total matching items across all pages.
    """

    items: list[T] = Field(default_factory=list)
    page_info: PageInfo
    total_count: int = 0
