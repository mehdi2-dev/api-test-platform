"""Uygulama ayarları.

Değerler sırasıyla ortam değişkenlerinden, sonra proje kökündeki .env dosyasından okunur.
Yeni bir ayar eklemek için Settings sınıfına alan eklemek yeterlidir.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> proje kökü (api-test-platform/)
ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "API Test Otomasyon Platformu"
    environment: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"
    # .env içinde virgülle ayrılmış yazılır: http://localhost:5173,http://127.0.0.1:5173
    cors_origins: str = "http://localhost:5173"

    database_url: str = "postgresql+psycopg://apitest:apitest@localhost:5432/apitest"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "degistir-beni"

    @field_validator("log_level")
    @classmethod
    def upper_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
