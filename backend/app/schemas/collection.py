"""Koleksiyon şemaları (ATOP-37..40)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.test_run import RunStatus
from app.schemas.assertion import TestRunRead
from app.services import jsonpath
from app.services.variables import VARIABLE_NAME

VARIABLE_PATTERN = f"^{VARIABLE_NAME}$"


class Extraction(BaseModel):
    """Cevaptan bir değer alıp sonraki adımlar için değişkene yazar (ATOP-38).

    source:
        json_path    -> path: "$.access_token"
        header       -> path: "Location"
        status_code  -> path gerekmez
    secret: değer sonuç ekranlarında ******** gösterilir (token gibi değerler için)
    """

    variable: str = Field(min_length=1, max_length=100, pattern=VARIABLE_PATTERN)
    source: Literal["json_path", "header", "status_code"] = "json_path"
    path: str | None = Field(default=None, max_length=500)
    secret: bool = False

    @model_validator(mode="after")
    def check_path(self) -> "Extraction":
        if self.source == "status_code":
            self.path = None
            return self
        self.path = (self.path or "").strip()
        if not self.path:
            raise ValueError(f"'{self.variable}' için yol (path) gerekli")
        if self.source == "json_path":
            jsonpath.parse(self.path)
        return self


class CollectionItemIn(BaseModel):
    api_definition_id: int
    enabled: bool = True
    extractions: list[Extraction] = Field(default_factory=list, max_length=20)


class CollectionItemRead(BaseModel):
    id: int
    position: int
    api_definition_id: int
    api_name: str
    method: str
    url: str
    enabled: bool
    extractions: list[Extraction]


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("Koleksiyon adı boş olamaz")
    return value


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    stop_on_failure: bool = False
    items: list[CollectionItemIn] = Field(
        default_factory=list, max_length=100, description="Sıra, listedeki sıradır"
    )

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_name(value)


class CollectionUpdate(BaseModel):
    """Gönderilen alanlar değişir. items gönderilirse adımların tamamı ve sırası yenilenir."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    stop_on_failure: bool | None = None
    items: list[CollectionItemIn] | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return _clean_name(value)


class CollectionRead(BaseModel):
    id: int
    name: str
    description: str | None
    stop_on_failure: bool
    items: list[CollectionItemRead]
    created_at: datetime
    updated_at: datetime


class CollectionSummary(BaseModel):
    id: int
    name: str
    description: str | None
    stop_on_failure: bool
    item_count: int
    last_run_status: RunStatus | None = None
    last_run_at: datetime | None = None
    updated_at: datetime


# --- Çalıştırma ---

StepStatus = Literal["passed", "failed", "error", "skipped"]


class ExtractedValue(BaseModel):
    variable: str
    found: bool
    value: str | None = Field(default=None, description="Gizli değişkenlerde ********")


class StepResult(BaseModel):
    position: int
    api_definition_id: int | None
    api_name: str
    method: str
    status: StepStatus
    test_run_id: int | None = None
    message: str | None = None
    extracted: list[ExtractedValue] = Field(default_factory=list)


class CollectionRunSummary(BaseModel):
    id: int
    collection_id: int | None
    collection_name: str
    environment_name: str | None
    state: Literal["queued", "running", "completed"] = Field(
        description="queued: kuyrukta, running: çalışıyor, completed: bitti (ATOP-44)"
    )
    trigger: Literal["manual", "schedule"] = "manual"
    schedule_id: int | None = None
    status: RunStatus | None = Field(description="Sonuç; bitene kadar boş")
    error: str | None = Field(default=None, description="Çalıştırma başlayamadıysa nedeni")
    total_steps: int
    passed_steps: int
    failed_steps: int
    skipped_steps: int
    elapsed_ms: float
    triggered_by_id: int | None
    created_at: datetime


class CollectionRunRead(CollectionRunSummary):
    steps: list[StepResult]
    step_runs: dict[int, TestRunRead] = Field(
        default_factory=dict, description="test_run_id -> adımın istek/cevap/kural detayı"
    )


# --- İçe / dışa aktarma (ATOP-40) ---

EXPORT_FORMAT = "api-test-platform/collection"
EXPORT_VERSION = 1


class ExportedApi(BaseModel):
    name: str
    description: str | None = None
    method: str
    url: str
    headers: list[dict[str, Any]] = Field(default_factory=list)
    query_params: list[dict[str, Any]] = Field(default_factory=list)
    body_type: str = "none"
    body: str | None = None
    auth: dict[str, Any] = Field(default_factory=lambda: {"type": "none"})
    assertions: list[dict[str, Any]] = Field(default_factory=list)


class ExportedStep(BaseModel):
    api: int = Field(ge=0, description="apis listesindeki sıra numarası")
    enabled: bool = True
    extractions: list[Extraction] = Field(default_factory=list)


class CollectionExport(BaseModel):
    format: Literal["api-test-platform/collection"] = EXPORT_FORMAT
    version: int = EXPORT_VERSION
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    stop_on_failure: bool = False
    apis: list[ExportedApi] = Field(default_factory=list, max_length=100)
    steps: list[ExportedStep] = Field(default_factory=list, max_length=100)
    required_variables: list[str] = Field(
        default_factory=list,
        description="Gizli değerler dosyaya yazılmaz; bunları ortama değişken olarak ekleyin",
    )

    @model_validator(mode="after")
    def check_references(self) -> "CollectionExport":
        for step in self.steps:
            if step.api >= len(self.apis):
                raise ValueError(f"Adım geçersiz API'ye işaret ediyor: {step.api}")
        return self


class ImportResult(BaseModel):
    collection: CollectionRead
    created_apis: int
    required_variables: list[str]
