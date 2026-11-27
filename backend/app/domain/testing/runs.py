"""Bir isteğin gönderim sonucu ve test çalıştırma kaydı.

Her "Çalıştır" bir kayıt üretir: hangi API, hangi ortam, kim çalıştırdı, gönderilen istek
(gizli değerler maskeli), gelen cevap, süre ve her kuralın sonucu. Test geçmişi ve
dashboard bu kayıtlardan beslenir.

API tanımı silinse bile geçmiş kaybolmasın diye adı ve metodu ayrıca saklanır.
"""

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.domain.api_definitions import ApiDefinition
from app.domain.secrets import MASK
from app.domain.testing.masking import is_sensitive_path, mask_headers, mask_text
from app.domain.testing.rules import RuleResult
from app.domain.testing.variables import mask_secrets

# Saklanan cevap gövdesinin üst sınırı (karakter)
MAX_STORED_BODY = 50_000


class RunStatus(StrEnum):
    PASSED = "passed"  # cevap geldi ve tüm kurallar geçti
    FAILED = "failed"  # cevap geldi ama en az bir kural kaldı
    ERROR = "error"  # cevap hiç alınamadı (bağlantı, zaman aşımı, eksik değişken...)


@dataclass
class SentRequest:
    """Gerçekte gönderilen isteğin özeti (gizli değerler maskeli)."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class SendOutcome:
    """Bir isteği göndermenin sonucu. Hedef sunucu hata kodu dönse bile ok=True'dur;
    ok=False sadece cevap hiç alınamadığında (bağlantı, zaman aşımı...) olur."""

    ok: bool
    elapsed_ms: float
    request: SentRequest
    status_code: int | None = None
    size_bytes: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    body_json: Any | None = None
    truncated: bool = False
    error: str | None = None
    environment: str | None = None


def masked_for_display(outcome: SendOutcome, secrets: list[str]) -> SendOutcome:
    """Ekrana dönen cevapta da gizli değerler ve hassas alanlar maskelenir."""
    body, body_json = outcome.body, outcome.body_json
    masked_body = mask_text(outcome.body, secrets)
    if masked_body != outcome.body:
        body = masked_body
        body_json = json.loads(masked_body) if outcome.body_json is not None else None
    return replace(
        outcome, body=body, body_json=body_json, headers=mask_headers(outcome.headers, secrets)
    )


def run_status(outcome: SendOutcome, results: list[RuleResult]) -> RunStatus:
    if not outcome.ok:
        return RunStatus.ERROR
    return RunStatus.FAILED if any(not item.passed for item in results) else RunStatus.PASSED


def _masked_result(item: RuleResult, secrets: list[str]) -> dict[str, Any]:
    data = {**asdict(item), "type": item.type.value}
    if data.get("actual") is not None:
        data["actual"] = (
            MASK if is_sensitive_path(item.target) else mask_secrets(data["actual"], secrets)
        )
    return data


@dataclass(eq=False, kw_only=True)
class ApiTestRun:
    api_name: str
    method: str
    status: RunStatus
    api_definition_id: int | None = None
    environment_name: str | None = None
    triggered_by_id: int | None = None
    # Koleksiyonun bir adımı olarak çalıştıysa hangi koleksiyon çalıştırmasına ait
    collection_run_id: int | None = None
    status_code: int | None = None
    elapsed_ms: float = 0.0
    passed_count: int = 0
    failed_count: int = 0
    error: str | None = None
    # Gönderilen istek (maskeli), cevap (kısaltılmış, maskeli) ve kural sonuçları
    request: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] | None = None
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    id: int | None = None
    created_at: datetime | None = None

    @classmethod
    def record(
        cls,
        *,
        api: ApiDefinition,
        outcome: SendOutcome,
        results: list[RuleResult],
        triggered_by_id: int | None,
        collection_run_id: int | None = None,
        secrets: list[str] | None = None,
    ) -> "ApiTestRun":
        """Sonucu saklanacak hale getirir: gizli değerler maskelenir, gövde kısaltılır.

        Kurallar maskelenmemiş gerçek cevap üzerinde çalışmıştır; maskeleme sadece
        saklanan veriye uygulanır.
        """
        secrets = secrets or []
        response = None
        if outcome.ok:
            response = {
                "status_code": outcome.status_code,
                "headers": mask_headers(outcome.headers, secrets),
                "body": mask_text(outcome.body, secrets)[:MAX_STORED_BODY],
                "truncated": outcome.truncated or len(outcome.body) > MAX_STORED_BODY,
                "size_bytes": outcome.size_bytes,
            }

        return cls(
            api_definition_id=api.id,
            api_name=api.name,
            method=api.method.value,
            environment_name=outcome.environment,
            triggered_by_id=triggered_by_id,
            collection_run_id=collection_run_id,
            status=run_status(outcome, results),
            status_code=outcome.status_code,
            elapsed_ms=outcome.elapsed_ms,
            passed_count=sum(1 for item in results if item.passed),
            failed_count=sum(1 for item in results if not item.passed),
            error=mask_secrets(outcome.error, secrets) if outcome.error else None,
            request=asdict(outcome.request),
            response=response,
            assertion_results=[_masked_result(item, secrets) for item in results],
        )
