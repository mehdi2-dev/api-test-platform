"""Cipher portunun Fernet adaptörü (anahtar yönetimi crypto.py içinde)."""

from app.adapters.outbound.security import crypto
from app.domain.errors import SecretUnreadable


class FernetCipher:
    def encrypt(self, plain: str) -> str:
        return crypto.encrypt_text(plain)

    def decrypt(self, token: str) -> str:
        try:
            return crypto.decrypt_text(token)
        except ValueError as exc:
            raise SecretUnreadable(str(exc)) from exc
