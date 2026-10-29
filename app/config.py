from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./tracker.db"
    secret_key: str = "dev-only-secret-change-me-in-production-please"
    access_token_minutes: int = 60
    anthropic_api_key: str | None = None  # optional: LLM rewrites the answer
    llm_model: str = "claude-haiku-4-5"

    model_config = {"env_file": ".env"}


settings = Settings()
