"""Use case hataları: iş kuralı değil, uygulama akışıyla ilgili durumlar."""

from app.domain.errors import DomainError


class AuthenticationFailed(DomainError):
    """Kimlik doğrulanamadı (yanlış şifre, geçersiz token, pasif hesap...)."""


class TooManyAttempts(DomainError):
    """Çok fazla hatalı giriş denemesi; bir süre beklenmeli."""

    def __init__(self, retry_after: int) -> None:
        minutes = max(1, round(retry_after / 60))
        super().__init__(
            f"Çok fazla hatalı deneme. Yaklaşık {minutes} dakika sonra tekrar deneyin."
        )
        self.retry_after = retry_after


class InvalidToken(Exception):
    """Token'ın imzası bozuk, süresi dolmuş veya türü yanlış."""


class QueueUnavailable(DomainError):
    """Çalıştırma kuyruğa eklenemedi (Redis veya worker çalışmıyor olabilir)."""
