"""Test kuralları (assertion) ve sonuçları (ATOP-31..35).

Bir kural dört parçadan oluşur:
    type      neyi kontrol ediyoruz?   status_code | response_time | json_path | header
    target    nerede?                   JSONPath ($.data.id) veya header adı
    operator  nasıl?                    equals, in_range, less_than, exists, contains...
    expected  ne bekliyoruz?            "200", "2xx", "500", "ok", "^\\d+$"...

Örnek: {"type": "json_path", "target": "$.status", "operator": "equals", "expected": "ok"}
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.test_run import RunStatus
from app.services import jsonpath


class AssertionType(StrEnum):
    STATUS_CODE = "status_code"
    RESPONSE_TIME = "response_time"
    JSON_PATH = "json_path"
    HEADER = "header"


OPERATORS: dict[AssertionType, tuple[str, ...]] = {
    AssertionType.STATUS_CODE: ("equals", "not_equals", "in_range", "in_list"),
    AssertionType.RESPONSE_TIME: ("less_than",),
    AssertionType.JSON_PATH: (
        "exists",
        "not_exists",
        "equals",
        "not_equals",
        "contains",
        "matches",
        "type_is",
        "greater_than",
        "less_than",
    ),
    AssertionType.HEADER: ("exists", "not_exists", "equals", "contains"),
}
NO_EXPECTED = {"exists", "not_exists"}
NEEDS_TARGET = {AssertionType.JSON_PATH, AssertionType.HEADER}
JSON_TYPES = ("string", "number", "boolean", "object", "array", "null")

STATUS_RANGE = re.compile(r"^([1-5])xx$|^(\d{3})\s*-\s*(\d{3})$", re.IGNORECASE)


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


class Assertion(BaseModel):
    type: AssertionType
    target: str | None = Field(default=None, max_length=500)
    operator: str
    expected: str | None = Field(default=None, max_length=2000)
    enabled: bool = True

    @model_validator(mode="after")
    def check(self) -> "Assertion":
        allowed = OPERATORS[self.type]
        if self.operator not in allowed:
            raise ValueError(
                f"{self.type.value} için operatör şunlardan biri olmalı: {', '.join(allowed)}"
            )

        if self.type in NEEDS_TARGET:
            self.target = (self.target or "").strip()
            if not self.target:
                raise ValueError(f"{self.type.value} kuralı için hedef (target) gerekli")
        else:
            self.target = None

        if self.operator in NO_EXPECTED:
            self.expected = None
            return self._check_target()

        if self.expected is None or not self.expected.strip():
            raise ValueError(f"'{self.operator}' için beklenen değer (expected) gerekli")
        self.expected = self.expected.strip()

        # {{değişken}} içeren değerler çalışma anında çözülür; şimdi kontrol edilemez
        if "{{" in self.expected:
            return self._check_target()

        value = self.expected
        if self.type == AssertionType.STATUS_CODE:
            if self.operator in ("equals", "not_equals"):
                if not value.isdigit() or not 100 <= int(value) <= 599:
                    raise ValueError("Durum kodu 100-599 arası bir sayı olmalı")
            elif self.operator == "in_range":
                if not STATUS_RANGE.match(value):
                    raise ValueError("Aralık '2xx' veya '200-299' biçiminde olmalı")
            elif self.operator == "in_list":
                items = [item.strip() for item in value.split(",")]
                if not items or not all(item.isdigit() for item in items):
                    raise ValueError("Liste virgülle ayrılmış durum kodları olmalı: 200,201,204")
        elif self.type == AssertionType.RESPONSE_TIME:
            if not _is_number(value) or float(value) <= 0:
                raise ValueError("Süre eşiği pozitif bir sayı (ms) olmalı")
        elif self.operator == "type_is":
            if value not in JSON_TYPES:
                raise ValueError(f"Tip şunlardan biri olmalı: {', '.join(JSON_TYPES)}")
        elif self.operator == "matches":
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"Geçersiz düzenli ifade (regex): {exc}") from exc
        elif self.operator in ("greater_than", "less_than"):
            if not _is_number(value):
                raise ValueError("Karşılaştırma için sayı girin")

        return self._check_target()

    def _check_target(self) -> "Assertion":
        if self.type == AssertionType.JSON_PATH and "{{" not in (self.target or ""):
            jsonpath.parse(self.target or "")  # hatalıysa ValueError -> 422
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
