"""Pydantic schemas for the Home Assistant integration (feature 016).

Models match ``specs/016-ha-integration/contracts/home-assistant-api.md``
sections 1 and 2. ``access_token`` is input-only — it is a field on
``HAConnectionUpsert`` but never appears in any response model. Redacted
read-back uses ``HAConnectionRead.token_masked``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


HAConnectionStatus = Literal[
    "ok",
    "auth_failure",
    "unreachable",
    "unexpected_payload",
    "not_configured",
]


class HAConnectionRead(BaseModel):
    """Redacted read-back of the singleton HA connection row.

    ``configured == False`` implies ``base_url`` / ``token_masked`` /
    ``last_success_at`` / ``last_error`` / ``last_error_at`` are ``None``.
    The plaintext access token is never returned — only the masked form.
    """

    configured: bool
    base_url: str | None = None
    token_masked: str | None = None
    status: HAConnectionStatus
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None


class HAConnectionUpsert(BaseModel):
    """Input-only payload for PUT/test-connection.

    ``access_token`` is never serialized into any response; it flows from
    the UI into the encrypt-and-store path and is then discarded from the
    request scope.
    """

    base_url: str = Field(..., min_length=1)
    access_token: str = Field(..., min_length=1)


class HAEntityOut(BaseModel):
    """One entity in the snapshot response (contract §2)."""

    entity_id: str
    ha_device_id: str
    domain: str
    friendly_name: str
    state: str
    last_changed: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)


class HAEntitiesResponse(BaseModel):
    """GET /ha/entities response body (contract §2)."""

    connection_status: HAConnectionStatus
    polled_at: datetime | None = None
    stale: bool = False
    entities: list[HAEntityOut] = Field(default_factory=list)


# ── Thread topology (contract §3, US-2) ─────────────────────────────────


class ThreadBorderRouterOut(BaseModel):
    """One Thread border router in the topology response."""

    ha_device_id: str
    friendly_name: str
    model: str | None = None
    online: bool
    attached_device_count: int


class ThreadDeviceOut(BaseModel):
    """One Thread end-device in the topology response."""

    ha_device_id: str
    friendly_name: str
    parent_border_router_id: str | None = None
    online: bool
    last_seen_parent_id: str | None = None


class ThreadTopologyResponse(BaseModel):
    """GET /ha/thread response body (contract §3)."""

    connection_status: HAConnectionStatus
    polled_at: datetime | None = None
    border_routers: list[ThreadBorderRouterOut] = Field(default_factory=list)
    devices: list[ThreadDeviceOut] = Field(default_factory=list)
    orphaned_device_count: int = 0
    empty_reason: Literal["no_thread_integration_data"] | None = None
