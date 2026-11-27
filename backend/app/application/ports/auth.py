"""Kimlik doğrulamayla ilgili portlar: token üretme/okuma ve giriş denemesi sınırı."""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.domain.users import User

TokenKind = Literal["access", "refresh"]


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    """Access token'ın kaç saniye geçerli olduğu."""


class TokenService(Protocol):
    def issue(self, user: User) -> TokenPair:
        """Kullanıcı için yeni access + refresh token üretir."""
        ...

    def user_id_from(self, token: str, kind: TokenKind) -> int:
        """Token'ı doğrulayıp sahibinin id'sini döndürür.

        Geçersizse app.application.errors.InvalidToken fırlatır.
        """
        ...


class LoginAttemptLimiter(Protocol):
    """Kaba kuvvet (brute-force) koruması için hatalı giriş sayacı."""

    def retry_after(self, key: str) -> int:
        """Kilitliyse kaç saniye beklenmeli; değilse 0."""
        ...

    def failed(self, key: str) -> None: ...

    def succeeded(self, key: str) -> None: ...
