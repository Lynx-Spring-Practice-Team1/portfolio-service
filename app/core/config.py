from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "portfolio-service"
    environment: str = "local"
    database_url: str = "postgresql+asyncpg://portfolio:portfolio@localhost:5434/portfolio_db"

    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_consumer_group: str = "portfolio-service"
    order_filled_topic: str = "order.filled"
    portfolio_updated_topic: str = "portfolio.updated"

    wallet_service_url: str | None = Field(default="http://localhost:8002")
    market_data_service_url: str | None = Field(default="http://localhost:8003")
    market_ws_enabled: bool = False
    market_ws_url: str | None = Field(default="ws://localhost:8080/ws")
    market_ws_api_key: str | None = None
    market_ws_api_secret: str | None = None
    market_ws_default_tickers: str = ""
    market_ws_resubscribe_seconds: int = 30
    price_cache_ttl_seconds: int = 15
    http_timeout_seconds: float = 3.0
    internal_service_token: str = Field(default="change-me-in-production", alias="INTERNAL_SERVICE_TOKEN")


@lru_cache
def get_settings() -> Settings:
    return Settings()
