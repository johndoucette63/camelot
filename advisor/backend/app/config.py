from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://john:changeme@postgres:5432/advisor"
    ollama_url: str = "http://ollama.holygrail"
    tz: str = "America/Denver"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
