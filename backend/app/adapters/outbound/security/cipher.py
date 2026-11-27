"""Cipher portunun Fernet adaptörü (anahtar yönetimi app.core.crypto içinde)."""

from app.core import crypto
from app.domain.errors import SecretUnreadable


class FernetCipher:
    def encrypt(self, plain: str) -> str:
        return crypto.encrypt_text(plain)

    def decrypt(self, token: str) -> str:
        try:
            return crypto.decrypt_text(token)
        except ValueError as exc:
            raise SecretUnreadable(str(exc)) from exc
