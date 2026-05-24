from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MetaAPI (master token used to provision user accounts)
    META_API_TOKEN: str = ""
    META_API_ACCOUNT_ID: str = ""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://trader:secret@localhost:5432/trading_bot"

    # API security (legacy single-key, kept for health/internal use)
    API_KEY: str = "changeme"

    # JWT
    JWT_SECRET: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Credential encryption
    ENCRYPTION_KEY: str = ""

    # Trading defaults
    DEFAULT_SYMBOL: str = "XAUUSD"
    DEFAULT_TIMEFRAME: str = "1m"
    DEFAULT_RISK_PERCENT: float = 1.0
    DEFAULT_MAX_OPEN_TRADES: int = 3
    DEFAULT_ATR_MULTIPLIER_SL: float = 1.5
    DEFAULT_ATR_MULTIPLIER_TP: float = 2.5

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"


settings = Settings()
