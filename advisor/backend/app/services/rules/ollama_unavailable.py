"""Ollama backend is unreachable."""
from __future__ import annotations

from datetime import timedelta

from app.services.rules.base import Rule, RuleContext, RuleResult


class OllamaUnavailableRule(Rule):
    id = "ollama_unavailable"
    name = "Ollama unavailable"
    severity = "info"
    sustained_window = timedelta(0)

    async def evaluate(self, ctx: RuleContext) -> list[RuleResult]:
        if ctx.ollama_healthy:
            return []
        return [
            RuleResult(
                target_type="system",
                target_id=None,
                message=(
                    "Ollama is not reachable — AI features are degraded "
                    "but rule-based monitoring is unaffected"
                ),
            )
        ]
