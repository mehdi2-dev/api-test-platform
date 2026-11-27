"""Koleksiyonlar: API'leri sıralı bir senaryoda birleştirir.

Örnek senaryo:
    1. Giriş yap           -> cevaptaki $.access_token'ı {{token}} olarak al
    2. Kullanıcıları listele (Authorization: Bearer {{token}})
    3. Yeni kullanıcı ekle -> cevaptaki $.id'yi {{user_id}} olarak al
    4. Kullanıcıyı getir   ({{base_url}}/users/{{user_id}})

Her adım bir API tanımına işaret eder; aynı API birden fazla koleksiyonda kullanılabilir.
Cevaptan değişken çıkarma ayarları (extractions) adıma aittir, API tanımına değil.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from app.domain.environments import Environment
from app.domain.errors import ProductionConfirmationRequired
from app.domain.secrets import MASK
from app.domain.testing import jsonpath
from app.domain.testing.rules import AssertionType, Response
from app.domain.testing.runs import RunStatus

MAX_SHOWN_VALUE = 200
STEP_STATUSES = ("passed", "failed", "error", "skipped")
# Değişken çıkarma başarısız olunca üretilen kural sonucunun tipi
SOURCE_TYPES = {
    "json_path": AssertionType.JSON_PATH,
    "header": AssertionType.HEADER,
    "status_code": AssertionType.STATUS_CODE,
}


class RunState(StrEnum):
    """Çalıştırmanın yaşam döngüsü. Sonuç (passed/failed/error) ayrı: status."""

    QUEUED = "queued"  # kuyruğa alındı, worker henüz başlamadı
    RUNNING = "running"  # adımlar çalışıyor
    COMPLETED = "completed"  # bitti; status alanında sonuç var


class RunTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"


# --- Cevaptan değişken çıkarma ---


class ExtractionRule(Protocol):
    variable: str
    source: str
    path: str | None
    secret: bool


@dataclass(frozen=True)
class Extraction:
    """Cevaptan bir değer alıp sonraki adımlar için değişkene yazar.

    source: json_path (path: "$.access_token"), header (path: "Location"), status_code
    secret: değer sonuç ekranlarında ******** gösterilir (token gibi değerler için)
    """

    variable: str
    source: str = "json_path"
    path: str | None = None
    secret: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Extraction":
        return cls(
            variable=data["variable"],
            source=data.get("source", "json_path"),
            path=data.get("path"),
            secret=bool(data.get("secret", False)),
        )


def extract_value(extraction: ExtractionRule, response: Response) -> str | None:
    """Cevaptan değeri metin olarak döndürür; bulunamazsa None."""
    if not response.ok or response.status_code is None:
        return None
    if extraction.source == "status_code":
        return str(response.status_code)
    if extraction.source == "header":
        lowered = {key.lower(): value for key, value in response.headers.items()}
        return lowered.get((extraction.path or "").lower())

    is_json = response.body_json is not None or response.body.strip() == "null"
    if not is_json:
        return None
    value = jsonpath.extract(response.body_json, extraction.path or "$")
    if value is jsonpath.MISSING:
        return None
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def shown_value(value: str, secret: bool) -> str:
    """Sonuç ekranında gösterilecek hali: gizliyse MASK, uzunsa kısaltılmış."""
    if secret:
        return MASK
    return value if len(value) <= MAX_SHOWN_VALUE else value[:MAX_SHOWN_VALUE] + "…"


# --- Koleksiyon ---


@dataclass(eq=False, kw_only=True)
class CollectionItem:
    """Koleksiyonun bir adımı.

    `api` (adımın API tanımı) bir ilişkidir ve tablo eşlemesinde tanımlanır; burada alan
    olarak yazılmaz, çünkü yeni adımda None olarak atanırsa api_definition_id'yi boşaltır.
    """

    api_definition_id: int
    position: int
    enabled: bool = True
    # [{"variable": "token", "source": "json_path", "path": "$.access_token", "secret": true}]
    extractions: list[dict[str, Any]] = field(default_factory=list)
    id: int | None = None
    collection_id: int | None = None

    @property
    def is_mutating(self) -> bool:
        api = getattr(self, "api", None)
        return api is not None and api.is_mutating


@dataclass(eq=False, kw_only=True)
class Collection:
    name: str
    description: str | None = None
    # Bir adım geçemezse kalan adımlar çalıştırılmasın mı?
    stop_on_failure: bool = False
    created_by_id: int | None = None
    items: list[CollectionItem] = field(default_factory=list)
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def enabled_items(self) -> list[CollectionItem]:
        return [item for item in self.items if item.enabled]

    def risky_steps(self) -> list[str]:
        """Veri değiştirebilecek etkin adımlar: 'POST Teklif oluştur' gibi."""
        return [
            f"{item.api.method.value} {item.api.name}"
            for item in self.enabled_items
            if item.is_mutating
        ]

    def ensure_production_confirmed(self, environment: Environment, confirmed: bool) -> None:
        """Production ortamında veri değiştiren adım varsa açık onay gerekir."""
        if not environment.is_production or confirmed:
            return
        risky = self.risky_steps()
        if risky:
            raise ProductionConfirmationRequired(
                f"'{environment.name}' bir Production ortamı ve koleksiyonda veri "
                f"değiştirebilecek adımlar var: {', '.join(risky)}. Emin misiniz?"
            )


# --- Çalıştırma ---


@dataclass
class ExtractedValue:
    variable: str
    found: bool
    value: str | None = None
    """Gizli değişkenlerde MASK."""


@dataclass
class StepResult:
    position: int
    api_definition_id: int | None
    api_name: str
    method: str
    status: str
    """passed | failed | error | skipped"""
    test_run_id: int | None = None
    message: str | None = None
    extracted: list[ExtractedValue] = field(default_factory=list)


@dataclass(eq=False, kw_only=True)
class CollectionRun:
    """Bir koleksiyonun bir kez çalıştırılması. Adımların detayı test çalıştırma kayıtlarında."""

    collection_name: str
    collection_id: int | None = None
    environment_name: str | None = None
    triggered_by_id: int | None = None
    # Sonuç; kuyrukta veya çalışırken henüz yok (None)
    status: RunStatus | None = None
    state: str = RunState.COMPLETED.value
    trigger: str = RunTrigger.MANUAL.value
    schedule_id: int | None = None
    # Çalıştırma hiç başlayamadıysa nedeni (kuyruk erişilemedi, ortam silindi...)
    error: str | None = None
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    elapsed_ms: float = 0.0
    # Adım özetleri: [{"position", "api_name", "status", "test_run_id", "extracted": [...]}]
    steps: list[dict[str, Any]] = field(default_factory=list)
    id: int | None = None
    created_at: datetime | None = None

    @classmethod
    def new(
        cls,
        collection: Collection,
        state: RunState,
        trigger: RunTrigger = RunTrigger.MANUAL,
        user_id: int | None = None,
        environment_name: str | None = None,
        schedule_id: int | None = None,
    ) -> "CollectionRun":
        return cls(
            collection_id=collection.id,
            collection_name=collection.name,
            environment_name=environment_name,
            triggered_by_id=user_id,
            state=state.value,
            trigger=trigger.value,
            schedule_id=schedule_id,
            total_steps=len(collection.enabled_items),
            steps=[],
        )

    def start(self, collection: Collection, environment_name: str | None) -> None:
        self.state = RunState.RUNNING.value
        self.environment_name = environment_name
        self.total_steps = len(collection.enabled_items)

    def record_progress(self, steps: list[StepResult]) -> None:
        """Canlı izleme için her adımdan sonra sayaçları ve adım özetlerini günceller."""
        counts = _count(steps)
        self.passed_steps = counts["passed"]
        self.failed_steps = counts["failed"] + counts["error"]
        self.skipped_steps = counts["skipped"]
        self.steps = [asdict(step) for step in steps]

    def complete(self, steps: list[StepResult], elapsed_ms: float) -> None:
        counts = _count(steps)
        self.total_steps = len(steps)
        self.elapsed_ms = elapsed_ms
        self.record_progress(steps)
        if steps and counts["passed"] == len(steps):
            self.status = RunStatus.PASSED
        elif counts["failed"]:
            self.status = RunStatus.FAILED
        else:
            self.status = RunStatus.ERROR if steps else RunStatus.PASSED
        self.state = RunState.COMPLETED.value

    def fail(self, message: str) -> None:
        """Çalıştırma başlayamadı veya yarıda kaldı."""
        self.state = RunState.COMPLETED.value
        self.status = RunStatus.ERROR
        self.error = message


def _count(steps: list[StepResult]) -> dict[str, int]:
    return {name: sum(1 for step in steps if step.status == name) for name in STEP_STATUSES}
