"""Kullanıcılarla ilgili portlar."""

from typing import Protocol

from app.domain.users import User


class UserRepository(Protocol):
    """Kullanıcıların saklandığı yer (SQLAlchemy, bellek...)."""

    def get(self, user_id: int) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...

    def list_all(self) -> list[User]:
        """id sırasına göre tüm kullanıcılar."""
        ...

    def count(self) -> int: ...

    def save(self, user: User) -> None:
        """Yeni kullanıcıyı ekler veya değişiklikleri kalıcı yapar; yeni kayda id verir."""
        ...


class PasswordHasher(Protocol):
    """Şifre özetleme (hash)."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, hashed_password: str) -> bool: ...
