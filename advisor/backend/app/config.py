import base64

from pydantic import SecretStr, field_validator
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

    # ── Home Assistant integration (feature 016) ─────────────────────────
    # Fernet key for encrypting the HA long-lived access token at rest.
    # Required at startup; no default so a missing key fails loudly
    # (Constitution V: silent failures unacceptable).
    advisor_encryption_key: SecretStr = SecretStr("")
    ha_poll_interval_seconds: int = 60
    ha_request_timeout_seconds: int = 10
    ha_notify_retry_budget_seconds: int = 300

    @field_validator("advisor_encryption_key")
    @classmethod
    def _validate_fernet_key(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        if not raw:
            raise ValueError(
                "ADVISOR_ENCRYPTION_KEY is required (Fernet key, 32 URL-safe base64 bytes). "
                "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        try:
            decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
        except Exception as e:
            raise ValueError(f"ADVISOR_ENCRYPTION_KEY is not valid URL-safe base64: {e}") from e
        if len(decoded) != 32:
            raise ValueError(
                f"ADVISOR_ENCRYPTION_KEY decoded to {len(decoded)} bytes; Fernet requires 32."
            )
        return v

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
