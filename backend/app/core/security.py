"""Şifre özetleme (bcrypt) ve JWT token üretme/doğrulama.

İki tür token var:
- access:  her istekte gönderilir, kısa ömürlü (varsayılan 30 dk)
- refresh: sadece yeni access token almak için, uzun ömürlü (varsayılan 7 gün)
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def _create_token(subject: str, token_type: TokenType, lifetime: timedelta, **claims: Any) -> str:
    now = datetime.now(UTC)
    payload = {"sub": subject, "type": token_type, "iat": now, "exp": now + lifetime, **claims}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(str(user_id), "access", lifetime, role=role)


def create_refresh_token(user_id: int) -> str:
    lifetime = timedelta(days=settings.refresh_token_expire_days)
    return _create_token(str(user_id), "refresh", lifetime)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Token'ı doğrular.

    İmza bozuksa, süresi dolmuşsa veya türü yanlışsa jwt.PyJWTError fırlatır.
    """
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Beklenen token türü: {expected_type}")
    return payload
