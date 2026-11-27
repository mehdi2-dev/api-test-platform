"""API tanımlarıyla ilgili portlar."""

from typing import Protocol

from app.domain.api_definitions import ApiDefinition


class ApiDefinitionRepository(Protocol):
    def get(self, api_id: int) -> ApiDefinition | None: ...

    def search(self, name_contains: str | None = None) -> list[ApiDefinition]:
        """Ada göre (büyük/küçük harf duyarsız) arar; ada, sonra id'ye göre sıralı."""
        ...

    def save(self, api: ApiDefinition) -> None: ...

    def delete(self, api: ApiDefinition) -> None: ...
