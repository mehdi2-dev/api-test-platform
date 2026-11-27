"""Test kuralları (assertion) ve sonuçları için HTTP şemaları.

Kural modeli ve doğrulaması domain'dedir (app.domain.testing.rules); burada sadece
pydantic ile HTTP giriş/çıkışına uyarlanır. Kural tipleri ve operatörler oradan gelir.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain.errors import InvalidInput
from app.domain.testing.rules import (  # noqa: F401  (eski import'lar için yeniden dışa aktarım)
    JSON_TYPES,
    NEEDS_TARGET,
    NO_EXPECTED,
    OPERATORS,
    STATUS_RANGE,
    AssertionType,
    normalize_rule,
)
from app.domain.testing.runs import RunStatus


class Assertion(BaseModel):
    type: AssertionType
    target: str | None = Field(default=None, max_length=500)
    operator: str
    expected: str | None = Field(default=None, max_length=2000)
    enabled: bool = True

    @model_validator(mode="after")
    def check(self) -> "Assertion":
        try:
            self.target, self.expected = normalize_rule(
                self.type, self.operator, self.target, self.expected
            )
        except InvalidInput as exc:
            raise ValueError(exc.message) from exc
        return self


class AssertionResult(BaseModel):
    type: AssertionType
    target: str | None = None
    operator: str
    expected: str | None = None
    passed: bool
    actual: str | None = Field(default=None, description="Cevapta bulunan değer (kısaltılmış)")
    message: str


class TestRunSummary(BaseModel):
    __test__ = False  # pytest bunu test sınıfı sanmasın

    id: int
    api_definition_id: int | None
    api_name: str
    method: str
    environment_name: str | None
    status: RunStatus
    status_code: int | None
    elapsed_ms: float
    passed_count: int
    failed_count: int
    error: str | None
    triggered_by_id: int | None
    collection_run_id: int | None = None
    created_at: datetime


class TestRunRead(TestRunSummary):
    __test__ = False

    request: dict[str, Any]
    response: dict[str, Any] | None
    assertion_results: list[AssertionResult]
