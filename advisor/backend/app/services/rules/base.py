"""Base types for the rule engine.

Rules return lists of RuleResult from their async evaluate() method. The
engine handles dedup, state transitions, cool-down, mute suppression, and
notification delivery — rules stay pure and side-effect-free.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.device import Device
    from app.models.health_check_result import HealthCheckResult
    from app.models.scan import Scan
    from app.models.service_definition import ServiceDefinition


Severity = Literal["info", "warning", "critical"]
TargetType = Literal["device", "service", "system", "ha_connection"]


@dataclass
class RuleResult:
    target_type: TargetType
    target_id: int | None
    message: str
    rule_id_override: str | None = None
    """Optional per-result rule_id override used by unknown_device to encode the MAC."""


@dataclass
class RuleContext:
    now: datetime
    session: "AsyncSession"
    devices: list["Device"] = field(default_factory=list)
    services: list["ServiceDefinition"] = field(default_factory=list)
    health_results: dict[int, "HealthCheckResult"] = field(default_factory=dict)
    container_state: dict = field(default_factory=dict)
    thresholds: dict[str, Decimal] = field(default_factory=dict)
    ollama_healthy: bool = True
    recent_scans: list["Scan"] = field(default_factory=list)
    device_metrics: dict[int, dict[str, float]] = field(default_factory=dict)
    """Optional per-device metric snapshot (cpu_percent, disk_percent, ...).

    Currently populated as an empty dict by the engine — metric collection is
    a future feature. Rules read from this dict and gracefully skip devices
    with no metrics on record so they degrade to no-ops in production until
    a metric source is wired in.
    """


class Rule:
    """Abstract base class for a rule.

    Subclasses override ``id``, ``name``, ``severity``, optionally
    ``sustained_window``, and implement ``evaluate``.

    Optional escalation hook: subclasses may set ``escalation_threshold`` to
    an integer N and override ``on_escalate`` to opt in to per-target
    escalation handling. The engine increments a per-(rule_id, target)
    consecutive-fire counter and, on hitting N, invokes ``on_escalate``
    exactly once per breach episode (reset on auto-resolve). The optional
    return value of ``on_escalate`` becomes a follow-up RuleResult emitted
    by the engine on the same cycle (typically with rule_id_override set
    to ``"<rule_id>:remediation"`` so it is distinguishable).

    Escalation count is in-memory only — see 015 spec data-model.md E5
    "Escalation counter persistence — explicit tradeoff".
    """

    id: str = ""
    name: str = ""
    severity: Severity = "info"
    sustained_window: timedelta = timedelta(minutes=5)
    escalation_threshold: int | None = None

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        raise NotImplementedError

    async def on_escalate(
        self, result: RuleResult, ctx: RuleContext
    ) -> RuleResult | None:
        """Called when the consecutive-fire count hits escalation_threshold.

        Side effects (e.g., docker stop) belong here. The optional return
        value is processed as an additional RuleResult by the engine and
        typically uses ``rule_id_override`` to distinguish remediation
        alerts from the original leak alerts.

        Default is a no-op; rules that opt in must override.
        """
        return None
