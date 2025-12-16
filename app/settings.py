from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    F95_USERNAME: str
    F95_PASSWORD: str
    DATABASE_URL: str = "sqlite+aiosqlite:///data/avn_index.db"
    F95CHECKER_DAILY_LIMIT: int = 1000
    SYNC_INTERVAL_HOURS: int = 6
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
