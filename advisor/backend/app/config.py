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

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
