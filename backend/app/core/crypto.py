"""Hassas verilerin (token, şifre, API anahtarı) veritabanında şifreli saklanması.

Fernet kullanılır (AES şifreleme + HMAC imza): veri hem okunamaz hem de
değiştirilirse fark edilir. Anahtar ENCRYPTION_KEY ayarından gelir; boşsa
SECRET_KEY'den türetilir. Anahtar değişirse eski kayıtlar çözülemez, bu yüzden
prod'da sabit ve gizli tutulmalıdır.

Not: Şifre (password) hash'lenir, geri çevrilemez. Token ise şifrelenir, çünkü
istek gönderirken asıl değerine geri ihtiyacımız var.
"""

import base64
import hashlib
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@lru_cache
def _fernet() -> Fernet:
    if settings.encryption_key:
        return Fernet(settings.encryption_key.encode())
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_text(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Şifreli veri çözülemedi (anahtar değişmiş olabilir)") from exc


def encrypt_json(data: dict[str, Any]) -> str:
    return encrypt_text(json.dumps(data, ensure_ascii=False))


def decrypt_json(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    return json.loads(decrypt_text(token))
