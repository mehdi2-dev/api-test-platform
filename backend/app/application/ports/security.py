"""Gizli verilerin şifrelenmesi için port."""

from typing import Protocol


class Cipher(Protocol):
    """Geri çözülebilir şifreleme (token, API anahtarı, gizli değişken...)."""

    def encrypt(self, plain: str) -> str: ...

    def decrypt(self, token: str) -> str:
        """Çözemezse app.domain.errors.SecretUnreadable fırlatır."""
        ...
