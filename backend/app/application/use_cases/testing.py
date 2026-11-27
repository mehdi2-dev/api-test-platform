"""Use case'ler: bir API'yi tek başına gönderme ve test olarak çalıştırma."""

from app.application.ports.testing import ApiSender, ApiTestRunRepository
from app.application.use_cases.api_definitions import PrepareApiRequest, PreparedRequest
from app.domain.testing.engine import evaluate
from app.domain.testing.runs import ApiTestRun, SendOutcome, masked_for_display
from app.domain.users import User


def _send(sender: ApiSender, prepared: PreparedRequest) -> SendOutcome:
    return sender.send(
        prepared.api,
        prepared.auth,
        variables=prepared.variables,
        secrets=prepared.secrets,
        environment_name=prepared.environment_name,
    )


class SendApiRequest:
    """İsteği gönderir ve cevabı gösterir; sonuç kaydedilmez, kurallar uygulanmaz."""

    def __init__(self, prepare: PrepareApiRequest, sender: ApiSender) -> None:
        self._prepare = prepare
        self._sender = sender

    def __call__(
        self, api_id: int, *, environment_id: int | None = None, confirm_production: bool = False
    ) -> SendOutcome:
        prepared = self._prepare(
            api_id, environment_id=environment_id, confirm_production=confirm_production
        )
        return masked_for_display(_send(self._sender, prepared), prepared.secrets)


class RunApiTest:
    """Gönderir, API'nin kurallarını cevaba uygular ve sonucu test geçmişine kaydeder."""

    def __init__(
        self, prepare: PrepareApiRequest, sender: ApiSender, runs: ApiTestRunRepository
    ) -> None:
        self._prepare = prepare
        self._sender = sender
        self._runs = runs

    def __call__(
        self,
        api_id: int,
        *,
        user: User,
        environment_id: int | None = None,
        confirm_production: bool = False,
    ) -> ApiTestRun:
        prepared = self._prepare(
            api_id, environment_id=environment_id, confirm_production=confirm_production
        )
        outcome = _send(self._sender, prepared)
        results = evaluate(prepared.api.assertions or [], outcome, prepared.variables)
        run = ApiTestRun.record(
            api=prepared.api,
            outcome=outcome,
            results=results,
            triggered_by_id=user.id,
            secrets=prepared.secrets,
        )
        self._runs.add(run)
        return run
