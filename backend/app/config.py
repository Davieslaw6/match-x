from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./matchx.db"
    env: str = "development"
    timezone: str = "UTC"
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    session_hours: int = 12
    llm_provider: str = "unconfigured"  # unconfigured | mock | openai_compatible
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    odds_stale_minutes: int = 180
    rate_limit_enabled: bool = True
    upload_dir: str = "./uploads_private"
    vision_provider: str = "unconfigured"
    cors_origin: str = ""

settings = Settings()
