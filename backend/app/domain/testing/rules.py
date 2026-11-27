"""Test kuralları (assertion), sonuçları ve kuralın uygulandığı cevap.

Bir kural dört parçadan oluşur:
    type      neyi kontrol ediyoruz?   status_code | response_time | json_path | header
    target    nerede?                   JSONPath ($.data.id) veya header adı
    operator  nasıl?                    equals, in_range, less_than, exists, contains...
    expected  ne bekliyoruz?            "200", "2xx", "500", "ok", "^\\d+$"...

Örnek: {"type": "json_path", "target": "$.status", "operator": "equals", "expected": "ok"}
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.domain.errors import InvalidInput
from app.domain.testing import jsonpath


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
MAX_TARGET_CHARS = 500
MAX_EXPECTED_CHARS = 2000


class Response(Protocol):
    """Kuralların uygulandığı cevap. İsteği gönderen adaptörün sonucu bu alanları taşır."""

    ok: bool
    status_code: int | None
    elapsed_ms: float
    headers: dict[str, str]
    body: str
    body_json: Any | None


@dataclass(frozen=True)
class Rule:
    type: AssertionType
    operator: str
    target: str | None = None
    expected: str | None = None
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        """Saklanan kuralı doğrulayıp oluşturur; geçersizse InvalidInput."""
        try:
            kind = AssertionType(data.get("type"))
        except ValueError as exc:
            choices = ", ".join(item.value for item in AssertionType)
            raise InvalidInput(f"type şunlardan biri olmalı: {choices}") from exc
        operator = data.get("operator")
        if not isinstance(operator, str):
            raise InvalidInput("operator gerekli")
        target, expected = data.get("target"), data.get("expected")
        for name, value, limit in [
            ("target", target, MAX_TARGET_CHARS),
            ("expected", expected, MAX_EXPECTED_CHARS),
        ]:
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                raise InvalidInput(f"{name} en fazla {limit} karakterlik bir metin olmalı")
        target, expected = normalize_rule(kind, operator, target, expected)
        return cls(
            type=kind,
            operator=operator,
            target=target,
            expected=expected,
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(frozen=True)
class RuleResult:
    type: AssertionType
    operator: str
    passed: bool
    message: str
    target: str | None = None
    expected: str | None = None
    actual: str | None = None
    """Cevapta bulunan değer (kısaltılmış)."""


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _check_target(kind: AssertionType, target: str | None) -> None:
    if kind == AssertionType.JSON_PATH and "{{" not in (target or ""):
        try:
            jsonpath.parse(target or "")
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc


def normalize_rule(
    kind: AssertionType, operator: str, target: str | None, expected: str | None
) -> tuple[str | None, str | None]:
    """Kuralı doğrular ve temizlenmiş (target, expected) döndürür; geçersizse InvalidInput.

    {{değişken}} içeren değerler çalışma anında çözüleceği için şimdi kontrol edilmez.
    """
    allowed = OPERATORS[kind]
    if operator not in allowed:
        raise InvalidInput(
            f"{kind.value} için operatör şunlardan biri olmalı: {', '.join(allowed)}"
        )

    if kind in NEEDS_TARGET:
        target = (target or "").strip()
        if not target:
            raise InvalidInput(f"{kind.value} kuralı için hedef (target) gerekli")
    else:
        target = None

    if operator in NO_EXPECTED:
        _check_target(kind, target)
        return target, None

    if expected is None or not expected.strip():
        raise InvalidInput(f"'{operator}' için beklenen değer (expected) gerekli")
    value = expected.strip()

    if "{{" not in value:
        if kind == AssertionType.STATUS_CODE:
            if operator in ("equals", "not_equals"):
                if not value.isdigit() or not 100 <= int(value) <= 599:
                    raise InvalidInput("Durum kodu 100-599 arası bir sayı olmalı")
            elif operator == "in_range":
                if not STATUS_RANGE.match(value):
                    raise InvalidInput("Aralık '2xx' veya '200-299' biçiminde olmalı")
            elif operator == "in_list":
                items = [item.strip() for item in value.split(",")]
                if not items or not all(item.isdigit() for item in items):
                    raise InvalidInput("Liste virgülle ayrılmış durum kodları olmalı: 200,201,204")
        elif kind == AssertionType.RESPONSE_TIME:
            if not _is_number(value) or float(value) <= 0:
                raise InvalidInput("Süre eşiği pozitif bir sayı (ms) olmalı")
        elif operator == "type_is":
            if value not in JSON_TYPES:
                raise InvalidInput(f"Tip şunlardan biri olmalı: {', '.join(JSON_TYPES)}")
        elif operator == "matches":
            try:
                re.compile(value)
            except re.error as exc:
                raise InvalidInput(f"Geçersiz düzenli ifade (regex): {exc}") from exc
        elif operator in ("greater_than", "less_than"):
            if not _is_number(value):
                raise InvalidInput("Karşılaştırma için sayı girin")

    _check_target(kind, target)
    return target, value
