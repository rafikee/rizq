from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rizq_mode: str = "paper"

    alpaca_paper_api_key: str
    alpaca_paper_secret_key: str
    alpaca_paper_base_url: str = "https://paper-api.alpaca.markets"

    databento_api_key: str | None = None

    database_path: str = "./data/rizq.db"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    s = Settings()  # type: ignore[call-arg]
    if s.rizq_mode != "paper":
        raise ValueError(
            f"RIZQ_MODE must be 'paper'. Got {s.rizq_mode!r}. Live is not implemented."
        )
    if "paper-api.alpaca.markets" not in s.alpaca_paper_base_url:
        raise ValueError(
            f"ALPACA_PAPER_BASE_URL must point at the paper endpoint. "
            f"Got {s.alpaca_paper_base_url!r}."
        )
    return s
