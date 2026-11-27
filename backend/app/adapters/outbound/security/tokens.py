"""TokenService portunun JWT adaptörü.

İki tür token var:
- access:  her istekte gönderilir, kısa ömürlü (varsayılan 30 dk)
- refresh: sadece yeni access token almak için, uzun ömürlü (varsayılan 7 gün)
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.application.errors import InvalidToken
from app.application.ports.auth import TokenKind, TokenPair
from app.core.config import settings
from app.domain.users import User


class JwtTokenService:
    def __init__(
        self,
        secret_key: str,
        algorithm: str,
        access_minutes: int,
        refresh_days: int,
    ) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_lifetime = timedelta(minutes=access_minutes)
        self._refresh_lifetime = timedelta(days=refresh_days)

    @classmethod
    def from_settings(cls) -> "JwtTokenService":
        return cls(
            settings.secret_key,
            settings.jwt_algorithm,
            settings.access_token_expire_minutes,
            settings.refresh_token_expire_days,
        )

    def _create(self, subject: str, kind: TokenKind, lifetime: timedelta, **claims: Any) -> str:
        now = datetime.now(UTC)
        payload = {"sub": subject, "type": kind, "iat": now, "exp": now + lifetime, **claims}
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_access_token(self, user_id: int, role: str) -> str:
        return self._create(str(user_id), "access", self._access_lifetime, role=role)

    def create_refresh_token(self, user_id: int) -> str:
        return self._create(str(user_id), "refresh", self._refresh_lifetime)

    def issue(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=self.create_access_token(user.id, user.role.value),
            refresh_token=self.create_refresh_token(user.id),
            expires_in=int(self._access_lifetime.total_seconds()),
        )

    def user_id_from(self, token: str, kind: TokenKind) -> int:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise InvalidToken(str(exc)) from exc
        if payload.get("type") != kind:
            raise InvalidToken(f"Beklenen token türü: {kind}")
        return int(payload["sub"])


def create_refresh_token(user_id: int) -> str:
    """Testler ve yardımcı araçlar için kısayol."""
    return JwtTokenService.from_settings().create_refresh_token(user_id)
