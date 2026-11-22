"""Hassas verilerin (token, şifre, API anahtarı, webhook adresi) şifreli saklanması (ATOP-49).

Fernet kullanılır (AES şifreleme + HMAC imza): veri hem okunamaz hem de değiştirilirse
fark edilir. Şifre (password) hash'lenir, geri çevrilemez; token ise şifrelenir, çünkü
istek gönderirken asıl değerine geri ihtiyacımız var.

Anahtar yönetimi:
    ENCRYPTION_KEY           yeni kayıtları şifreleyen anahtar (boşsa SECRET_KEY'den türetilir)
    ENCRYPTION_KEY_PREVIOUS  eski anahtar(lar), virgülle. Sadece ÇÖZMEK için denenir.

Anahtar değiştirme (rotasyon):
    1. Yeni anahtar üret:      docker compose exec backend python -m app.cli generate-key
    2. .env: ENCRYPTION_KEY=<yeni>, ENCRYPTION_KEY_PREVIOUS=<eski>; servisleri yeniden başlat
    3. Kayıtları yeni anahtarla yeniden şifrele:
                               docker compose exec backend python -m app.cli rotate-keys
    4. ENCRYPTION_KEY_PREVIOUS'ı boşalt, yeniden başlat
"""

import base64
import hashlib
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings


def derived_key(secret: str) -> bytes:
    """SECRET_KEY'den Fernet anahtarı türetir (ENCRYPTION_KEY verilmediğinde)."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


@lru_cache
def _fernet() -> MultiFernet:
    primary = settings.encryption_key.encode() if settings.encryption_key else None
    keys = [primary or derived_key(settings.secret_key)]
    keys += [
        item.strip().encode()
        for item in settings.encryption_key_previous.split(",")
        if item.strip()
    ]
    # Eskiden ENCRYPTION_KEY boşken SECRET_KEY'den türetilmiş olabilir: onu da çözmede dene
    if primary is not None:
        keys.append(derived_key(settings.secret_key))
    return MultiFernet([Fernet(key) for key in dict.fromkeys(keys)])


def reload_keys() -> None:
    """Ayarlar değiştiğinde (testler, CLI) anahtarları yeniden oku."""
    _fernet.cache_clear()


def encrypt_text(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_text(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Şifreli veri çözülemedi (anahtar değişmiş olabilir)") from exc


def rotate_text(token: str) -> str:
    """Eski anahtarla şifrelenmiş veriyi güncel anahtarla yeniden şifreler."""
    try:
        return _fernet().rotate(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Şifreli veri çözülemedi; eski anahtar ENCRYPTION_KEY_PREVIOUS'ta mı?"
        ) from exc


def encrypt_json(data: dict[str, Any]) -> str:
    return encrypt_text(json.dumps(data, ensure_ascii=False))


def decrypt_json(token: str | None) -> dict[str, Any]:
    if not token:
        return {}
    return json.loads(decrypt_text(token))
