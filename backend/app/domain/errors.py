"""Domain hataları: iş kuralı ihlalleri.

Domain HTTP bilmez; hangi hatanın hangi durum koduna döneceğine giren HTTP adaptörü
(app.adapters.inbound.http.errors) karar verir.
"""


class DomainError(Exception):
    """Tüm iş kuralı hatalarının atası."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationFailed(DomainError):
    """İstek bir iş kuralına uymuyor."""


class InvalidInput(DomainError):
    """Gönderilen değer işlenemiyor (ör. kayıtlı değeri olmayan gizli alan için MASK)."""


class NotFound(DomainError):
    """İstenen kayıt yok."""


class Conflict(DomainError):
    """Mevcut bir kayıtla çakışıyor."""


class AccessDenied(DomainError):
    """Bu işlem için yetki yok."""


class SecretUnreadable(DomainError):
    """Şifreli bir değer çözülemedi (şifreleme anahtarı değişmiş olabilir)."""
