from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    F95_USERNAME: str
    F95_PASSWORD: str
    DATABASE_URL: str = "sqlite+aiosqlite:///data/avn_index.db"
    SEED_STATE_FILE: str = "data/seed_state.json"
    F95CHECKER_DAILY_LIMIT: int = 1000
    SYNC_INTERVAL_HOURS: int = 6
    LOG_LEVEL: str = "INFO"
    LOG_JSON_FORMAT: bool = True
    LOG_DIR: str = "data/logs"
    SEED_PAGE_DELAY: int = 45
    SEARCH_FRESHNESS_DAYS: int = 7
    WEIGHTED_RATING_MIN_VOTES: int = 50
    WEIGHTED_RATING_GLOBAL_MEAN: float = 4.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
