"""Ortamlarla ilgili portlar."""

from typing import Protocol

from app.domain.environments import Environment


class EnvironmentRepository(Protocol):
    def get(self, environment_id: int) -> Environment | None: ...

    def get_by_name(self, name: str) -> Environment | None: ...

    def list_all(self) -> list[Environment]:
        """Önce Production olmayanlar, sonra ada göre sıralı."""
        ...

    def save(self, environment: Environment) -> None:
        """Ekler veya değişiklikleri (değişkenler dahil) kalıcı yapar."""
        ...

    def delete(self, environment: Environment) -> None: ...
