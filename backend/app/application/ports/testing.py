"""Test çalıştırmayla ilgili portlar: isteği gönderen ve sonucu saklayan."""

from typing import Any, Protocol

from app.domain.api_definitions import ApiDefinition
from app.domain.testing.runs import ApiTestRun, SendOutcome


class ApiSender(Protocol):
    """API tanımını gerçek bir HTTP isteğine çevirip gönderir.

    {{değişken}}'leri çözer, kimlik bilgisini ekler, süreyi ölçer. Ağ hatalarında
    istisna fırlatmaz; sonucu ok=False ve error alanıyla döndürür.
    """

    def send(
        self,
        api: ApiDefinition,
        auth: dict[str, Any],
        *,
        variables: dict[str, str],
        secrets: list[str],
        environment_name: str | None,
    ) -> SendOutcome: ...


class ApiTestRunRepository(Protocol):
    def add(self, run: ApiTestRun) -> None:
        """Kaydı saklar ve id verir."""
        ...
