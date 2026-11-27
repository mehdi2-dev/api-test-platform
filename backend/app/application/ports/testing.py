"""Test çalıştırmayla ilgili portlar: isteği gönderen ve sonucu saklayan."""

from datetime import datetime
from typing import Any, Protocol

from app.domain.api_definitions import ApiDefinition
from app.domain.reporting import RunHistoryFilter
from app.domain.testing.runs import ApiTestRun, RunStatus, SendOutcome


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

    def for_collection_run(self, collection_run_id: int) -> list[ApiTestRun]:
        """Bir koleksiyon çalıştırmasının adımlarına ait kayıtlar."""
        ...

    def get(self, run_id: int) -> ApiTestRun | None: ...

    def recent(
        self, *, api_id: int | None = None, status: RunStatus | None = None, limit: int = 20
    ) -> list[ApiTestRun]:
        """En yeni önce."""
        ...

    def search(
        self, filters: RunHistoryFilter, *, offset: int, limit: int
    ) -> tuple[int, list[ApiTestRun]]:
        """(filtreye uyan toplam kayıt, istenen sayfa); en yeni önce."""
        ...

    def since(self, moment: datetime) -> list[ApiTestRun]: ...

    def last_passed_before(self, api_definition_id: int, run_id: int) -> ApiTestRun | None:
        """Aynı API'nin bu kayıttan önceki son başarılı çalıştırması."""
        ...
