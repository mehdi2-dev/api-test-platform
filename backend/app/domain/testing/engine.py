"""Test motoru: kuralları bir cevaba uygular.

Her kural için Geçti/Kaldı, cevapta bulunan değer ve okunur bir mesaj üretir.
Kural ayarı bozuksa (ör. çalışma anında çözülen bir değişken sayı çıkmadıysa) program
çökmez; o kural "kaldı" sayılır ve mesajda nedeni yazar.
"""

import json
import re
from typing import Any

from app.domain.errors import InvalidInput
from app.domain.testing import jsonpath
from app.domain.testing.rules import STATUS_RANGE, AssertionType, Response, Rule, RuleResult
from app.domain.testing.variables import resolve

MAX_ACTUAL_CHARS = 200


class RuleError(ValueError):
    """Kuralın kendisi uygulanamıyor (ör. sayı beklenirken metin geldi)."""


def _show(value: Any) -> str:
    if value is jsonpath.MISSING:
        return "(yok)"
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= MAX_ACTUAL_CHARS else text[:MAX_ACTUAL_CHARS] + "…"


def _parse_expected(expected: str) -> Any:
    """'200' -> 200, 'true' -> True, '"ok"' -> 'ok', 'ok' -> 'ok' (JSON değilse metin)."""
    try:
        return json.loads(expected)
    except ValueError:
        return expected


def _equals(actual: Any, expected: str) -> bool:
    parsed = _parse_expected(expected)
    if isinstance(actual, bool) or isinstance(parsed, bool):
        return actual is parsed
    if actual == parsed:
        return True
    # "200" yazıp metin "200" bekleyen kullanıcı için: metin karşılaştırması
    return isinstance(actual, str) and actual == expected


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _number(text: str, what: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise RuleError(f"{what} sayı olmalı: '{text}'") from exc


def _check_status(rule: Rule, code: int) -> tuple[bool, str]:
    expected = rule.expected or ""
    if rule.operator in ("equals", "not_equals"):
        target = int(_number(expected, "Beklenen durum kodu"))
        ok = code == target
        if rule.operator == "equals":
            return ok, f"Beklenen {target}, gelen {code}"
        return not ok, f"{target} olmamalı, gelen {code}"
    if rule.operator == "in_range":
        match = STATUS_RANGE.match(expected)
        if not match:
            raise RuleError(f"Aralık '2xx' veya '200-299' biçiminde olmalı: '{expected}'")
        if match.group(1):
            low = int(match.group(1)) * 100
            high = low + 99
        else:
            low, high = int(match.group(2)), int(match.group(3))
        return low <= code <= high, f"Beklenen {expected} aralığı, gelen {code}"
    # in_list
    allowed = {int(_number(item.strip(), "Durum kodu")) for item in expected.split(",")}
    return code in allowed, f"Beklenen {expected} içinden biri, gelen {code}"


def _check_header(rule: Rule, headers: dict[str, str]) -> tuple[bool, Any, str]:
    name = (rule.target or "").lower()
    lowered = {key.lower(): value for key, value in headers.items()}
    actual = lowered.get(name, jsonpath.MISSING)
    present = actual is not jsonpath.MISSING
    if rule.operator == "exists":
        return present, actual, f"'{rule.target}' header'ı {'var' if present else 'yok'}"
    if rule.operator == "not_exists":
        return not present, actual, f"'{rule.target}' header'ı {'var' if present else 'yok'}"
    if not present:
        return False, actual, f"'{rule.target}' header'ı yok"
    expected = rule.expected or ""
    if rule.operator == "equals":
        return actual == expected, actual, f"Beklenen '{expected}'"
    return expected in actual, actual, f"'{expected}' içermeli"


def _check_json(rule: Rule, body_json: Any, is_json: bool) -> tuple[bool, Any, str]:
    if not is_json:
        return False, jsonpath.MISSING, "Cevap JSON değil"
    try:
        actual = jsonpath.extract(body_json, rule.target or "$")
    except ValueError as exc:
        raise RuleError(str(exc)) from exc

    present = actual is not jsonpath.MISSING
    op = rule.operator
    path = rule.target
    if op == "exists":
        return present, actual, f"{path} {'bulundu' if present else 'bulunamadı'}"
    if op == "not_exists":
        return not present, actual, f"{path} {'bulundu' if present else 'bulunamadı'}"
    if not present:
        return False, actual, f"{path} bulunamadı"

    expected = rule.expected or ""
    if op == "equals":
        return _equals(actual, expected), actual, f"Beklenen {expected}"
    if op == "not_equals":
        return not _equals(actual, expected), actual, f"{expected} olmamalı"
    if op == "contains":
        if isinstance(actual, str):
            ok = expected in actual
        elif isinstance(actual, list):
            parsed = _parse_expected(expected)
            ok = parsed in actual or expected in [str(item) for item in actual]
        elif isinstance(actual, dict):
            ok = expected in actual
        else:
            ok = expected in str(actual)
        return ok, actual, f"'{expected}' içermeli"
    if op == "matches":
        text = actual if isinstance(actual, str) else json.dumps(actual, ensure_ascii=False)
        try:
            ok = re.search(expected, text) is not None
        except re.error as exc:
            raise RuleError(f"Geçersiz düzenli ifade: {exc}") from exc
        return ok, actual, f"/{expected}/ ile eşleşmeli"
    if op == "type_is":
        kind = _json_type(actual)
        return kind == expected, actual, f"Beklenen tip {expected}, gelen {kind}"
    # greater_than / less_than
    if isinstance(actual, bool) or not isinstance(actual, int | float):
        return False, actual, f"Değer sayı değil ({_json_type(actual)})"
    limit = _number(expected, "Karşılaştırma değeri")
    if op == "greater_than":
        return actual > limit, actual, f"{limit:g} değerinden büyük olmalı"
    return actual < limit, actual, f"{limit:g} değerinden küçük olmalı"


def is_json_response(response: Response) -> bool:
    return response.body_json is not None or response.body.strip() == "null"


def evaluate_one(rule: Rule, response: Response) -> RuleResult:
    def result(passed: bool, message: str, actual: str | None = None) -> RuleResult:
        return RuleResult(
            type=rule.type,
            target=rule.target,
            operator=rule.operator,
            expected=rule.expected,
            passed=passed,
            actual=actual,
            message=message,
        )

    if not response.ok or response.status_code is None:
        return result(False, "Cevap alınamadı")

    try:
        if rule.type == AssertionType.STATUS_CODE:
            passed, message = _check_status(rule, response.status_code)
            actual: Any = response.status_code
        elif rule.type == AssertionType.RESPONSE_TIME:
            limit = _number(rule.expected or "", "Süre eşiği")
            passed = response.elapsed_ms < limit
            actual = response.elapsed_ms
            message = f"{limit:g} ms altında olmalı, sürdü {response.elapsed_ms:g} ms"
        elif rule.type == AssertionType.HEADER:
            passed, actual, message = _check_header(rule, response.headers)
        else:
            passed, actual, message = _check_json(
                rule, response.body_json, is_json_response(response)
            )
    except RuleError as exc:
        return result(False, f"Kural uygulanamadı: {exc}")

    return result(passed, message, _show(actual))


def evaluate(
    rules: list[dict[str, Any]], response: Response, variables: dict[str, str] | None = None
) -> list[RuleResult]:
    """Etkin kuralları sırayla uygular. Hedef ve beklenen değerdeki {{değişken}}'ler çözülür."""
    variables = variables or {}
    results: list[RuleResult] = []
    for raw in rules:
        if not raw.get("enabled", True):
            continue
        missing: set[str] = set()
        data = {
            **raw,
            "target": resolve(raw.get("target"), variables, missing),
            "expected": resolve(raw.get("expected"), variables, missing),
        }
        try:
            rule = Rule.from_dict(data)
        except InvalidInput as exc:
            try:
                kind = AssertionType(raw.get("type"))
            except ValueError:
                kind = AssertionType.JSON_PATH
            results.append(
                RuleResult(
                    type=kind,
                    target=raw.get("target"),
                    operator=raw.get("operator", "?"),
                    expected=raw.get("expected"),
                    passed=False,
                    message=f"Kural geçersiz: {exc.message}",
                )
            )
            continue
        if missing:
            results.append(
                RuleResult(
                    type=rule.type,
                    target=rule.target,
                    operator=rule.operator,
                    expected=rule.expected,
                    passed=False,
                    message=f"Tanımsız değişken: {', '.join(sorted(missing))}",
                )
            )
            continue
        results.append(evaluate_one(rule, response))
    return results
