"""Test adaptörleri: portların bellekte çalışan sahte uygulamaları.

Use case'ler bunlarla veritabanı, bcrypt veya JWT olmadan, milisaniyeler içinde test edilir.
"""

from app.application.errors import InvalidToken
from app.application.ports.auth import TokenKind, TokenPair
from app.domain.users import User


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[int, User] = {}
        self._next_id = 1

    def get(self, user_id: int) -> User | None:
        return self.items.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.items.values() if u.email == email), None)

    def list_all(self) -> list[User]:
        return [self.items[key] for key in sorted(self.items)]

    def count(self) -> int:
        return len(self.items)

    def save(self, user: User) -> None:
        if user.id is None:
            user.id = self._next_id
            self._next_id += 1
        self.items[user.id] = user


class PlainPasswordHasher:
    """Gerçek özet yerine okunabilir bir önek: 'hashed:<şifre>'."""

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, hashed_password: str) -> bool:
        return hashed_password == f"hashed:{password}"


class FakeTokenService:
    """Token olarak '<tür>:<kullanıcı id>' metnini kullanır."""

    def issue(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=f"access:{user.id}", refresh_token=f"refresh:{user.id}", expires_in=60
        )

    def user_id_from(self, token: str, kind: TokenKind) -> int:
        token_kind, _, user_id = token.partition(":")
        if token_kind != kind or not user_id.isdigit():
            raise InvalidToken("geçersiz")
        return int(user_id)


class FakeLoginLimiter:
    """Belirtilen sayıda hatalı denemeden sonra kilitlenen basit sayaç."""

    def __init__(self, max_attempts: int = 3, lock_seconds: int = 600) -> None:
        self.max_attempts = max_attempts
        self.lock_seconds = lock_seconds
        self.failures: dict[str, int] = {}

    def retry_after(self, key: str) -> int:
        return self.lock_seconds if self.failures.get(key, 0) >= self.max_attempts else 0

    def failed(self, key: str) -> None:
        self.failures[key] = self.failures.get(key, 0) + 1

    def succeeded(self, key: str) -> None:
        self.failures.pop(key, None)
