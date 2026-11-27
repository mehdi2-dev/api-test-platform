"""Test motoru (domain): kural doğrulama ve değerlendirme; HTTP ve pydantic olmadan.

Cevap olarak basit bir dataclass kullanıyoruz: motor sadece Response protokolündeki
alanlara bakar, cevabı kimin ürettiğini bilmez.
"""

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.domain.errors import InvalidInput
from app.domain.testing.engine import evaluate
from app.domain.testing.rules import AssertionType, Rule


@dataclass
class FakeResponse:
    ok: bool = True
    status_code: int | None = 200
    elapsed_ms: float = 120.0
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "application/json"})
    body: str = '{"status": "ok", "count": 3}'
    body_json: Any | None = field(default_factory=lambda: {"status": "ok", "count": 3})


def rule(type_: str, operator: str, expected=None, target=None, **extra) -> dict:
    return {"type": type_, "operator": operator, "expected": expected, "target": target, **extra}


# --- Kural doğrulama ---


def test_rule_is_normalized() -> None:
    parsed = Rule.from_dict(rule("json_path", "equals", " ok ", target=" $.status "))
    assert (parsed.type, parsed.target, parsed.expected) == (
        AssertionType.JSON_PATH,
        "$.status",
        "ok",
    )


def test_status_rule_drops_target_and_exists_drops_expected() -> None:
    assert Rule.from_dict(rule("status_code", "equals", "200", target="x")).target is None
    assert Rule.from_dict(rule("header", "exists", "x", target="X-Id")).expected is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (rule("status_code", "contains", "200"), "operatör"),
        (rule("json_path", "equals", "ok"), "hedef"),
        (rule("status_code", "equals", None), "beklenen değer"),
        (rule("status_code", "equals", "999"), "100-599"),
        (rule("status_code", "in_range", "2x"), "Aralık"),
        (rule("response_time", "less_than", "-5"), "pozitif"),
        (rule("json_path", "type_is", "sayı", target="$.a"), "Tip"),
        (rule("json_path", "matches", "(", target="$.a"), "regex"),
        (rule("json_path", "exists", target="$.["), "JSONPath"),
        (rule("ses", "equals", "1"), "type"),
    ],
)
def test_invalid_rules_are_rejected(data, message) -> None:
    with pytest.raises(InvalidInput, match=message):
        Rule.from_dict(data)


def test_values_with_variables_are_checked_at_run_time() -> None:
    assert Rule.from_dict(rule("status_code", "equals", "{{kod}}")).expected == "{{kod}}"


# --- Değerlendirme ---


def test_passing_and_failing_rules() -> None:
    passed, failed = evaluate(
        [
            rule("status_code", "equals", "200"),
            rule("json_path", "greater_than", "5", target="$.count"),
        ],
        FakeResponse(),
    )

    assert (passed.passed, passed.actual) == (True, "200")
    assert (failed.passed, failed.actual, failed.message) == (
        False,
        "3",
        "5 değerinden büyük olmalı",
    )


def test_disabled_rules_are_skipped() -> None:
    assert evaluate([rule("status_code", "equals", "500", enabled=False)], FakeResponse()) == []


def test_variables_are_resolved_and_missing_ones_reported() -> None:
    rules = [rule("json_path", "equals", "{{beklenen}}", target="$.status")]

    assert evaluate(rules, FakeResponse(), {"beklenen": "ok"})[0].passed is True
    missing = evaluate(rules, FakeResponse(), {})[0]
    assert (missing.passed, missing.message) == (False, "Tanımsız değişken: beklenen")


def test_invalid_stored_rule_fails_instead_of_crashing() -> None:
    [outcome] = evaluate([rule("status_code", "equals", "abc")], FakeResponse())
    assert outcome.passed is False
    assert outcome.message.startswith("Kural geçersiz:")


def test_no_response_fails_every_rule() -> None:
    [outcome] = evaluate(
        [rule("status_code", "equals", "200")], FakeResponse(ok=False, status_code=None)
    )
    assert (outcome.passed, outcome.message) == (False, "Cevap alınamadı")


def test_non_json_body_fails_json_rules() -> None:
    [outcome] = evaluate(
        [rule("json_path", "exists", target="$.a")], FakeResponse(body="merhaba", body_json=None)
    )
    assert outcome.message == "Cevap JSON değil"
