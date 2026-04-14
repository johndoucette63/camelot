from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://john:changeme@postgres:5432/advisor"
    ollama_url: str = "http://ollama.holygrail"
    ollama_model: str = "llama3.1:8b"
    tz: str = "America/Denver"

    rule_engine_interval_seconds: int = 60
    ai_narrative_timeout_seconds: int = 10
    ai_narrative_cache_seconds: int = 60
    ha_webhook_timeout_seconds: int = 5

    # ── VPN leak watchdog (feature 015) ──────────────────────────────────
    # Comma-separated list of IPs that, if observed as Deluge's external IP,
    # constitute a leak. AlertThreshold can't store lists (Numeric-only), so
    # this lives here and is read at engine time. Minimum required entry is
    # the home WAN IP — see FR-010 + Clarification Q1 in the 015 spec.
    vpn_leak_denylist_ips: str = "67.176.27.48"
    # SSH target on HOLYGRAIL → Torrentbox. Reuses passwordless SSH from
    # scripts/ssh-config; no new credentials.
    vpn_probe_ssh_target: str = "torrentbox"
    vpn_probe_container_name: str = "deluge"
    vpn_probe_timeout_seconds: int = 8
    # 3-strike auto-stop per Clarification Q2 + FR-012.
    vpn_leak_escalation_threshold: int = 3

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def vpn_leak_denylist_ips_set(self) -> set[str]:
        """Parse the comma-separated denylist into a set for membership checks."""
        return {ip.strip() for ip in self.vpn_leak_denylist_ips.split(",") if ip.strip()}


settings = Settings()
