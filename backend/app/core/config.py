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


DEFAULT_SECRETS = {
    "gelistirme-icin-varsayilan-anahtar-prodda-degistirin",
    "degistir-beni-uzun-ve-rastgele-bir-deger",
}


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

    # JWT imzalama anahtarı: prod'da mutlaka uzun ve rastgele bir değer verin
    secret_key: str = "gelistirme-icin-varsayilan-anahtar-prodda-degistirin"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Token/şifre gibi gizli değerleri şifreleyen Fernet anahtarı.
    # Boş bırakılırsa SECRET_KEY'den türetilir. Üretmek için:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = ""
    # Anahtar değiştirirken eski anahtar(lar), virgülle. Sadece çözmek için kullanılır.
    encryption_key_previous: str = ""

    # Giriş denemesi sınırı: aynı e-posta + IP için bu kadar hatalı denemeden sonra kilit
    login_max_attempts: int = 5
    login_lock_seconds: int = 15 * 60

    # Test edilen API'lere giden isteklerin zaman aşımı (saniye)
    request_timeout_seconds: float = 30.0

    # Zamanlanmış çalıştırmaların (cron) yorumlandığı saat dilimi
    timezone: str = "Europe/Istanbul"

    # Demo CRM servisinin Docker içindeki adresi (örnek senaryoların "Demo" ortamı)
    demo_base_url: str = "http://demo:8001"

    # Bildirim mesajlarındaki bağlantılar için arayüz adresi
    frontend_url: str = "http://localhost:5173"
    notification_timeout_seconds: float = 10.0

    # E-posta bildirimi (ATOP-48). smtp_host boşsa e-posta kanalları hata verir.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "api-test@localhost"
    smtp_use_tls: bool = True

    # Veritabanında hiç kullanıcı yoksa açılışta oluşturulan ilk admin
    first_admin_email: str = "admin@apitest.com"
    first_admin_password: str = "Admin12345"
    first_admin_name: str = "Sistem Yöneticisi"

    @field_validator("log_level")
    @classmethod
    def upper_log_level(cls, value: str) -> str:
        return value.upper()

    def security_warnings(self) -> list[str]:
        """Prod'a çıkmadan düzeltilmesi gereken ayarlar (ATOP-49)."""
        warnings = []
        if self.secret_key in DEFAULT_SECRETS or len(self.secret_key) < 32:
            warnings.append("SECRET_KEY varsayılan veya kısa (en az 32 karakter, rastgele olmalı)")
        if not self.encryption_key:
            warnings.append(
                "ENCRYPTION_KEY boş: gizli veriler SECRET_KEY'den türetilen anahtarla şifreleniyor"
            )
        if self.first_admin_password == "Admin12345":
            warnings.append("FIRST_ADMIN_PASSWORD varsayılan değerde")
        if "*" in self.cors_origin_list:
            warnings.append("CORS_ORIGINS '*' olmamalı")
        return warnings

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
