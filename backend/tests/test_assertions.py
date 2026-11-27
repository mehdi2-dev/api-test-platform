"""Test motoru (ATOP-31..35) testleri.

İlk bölüm motoru doğrudan dener (HTTP yok, sadece fonksiyonlar). İkinci bölüm
/run endpoint'i üzerinden uçtan uca çalışır ve sonucun kaydedildiğini kontrol eder.
"""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.apis import get_http_transport
from app.domain.testing import jsonpath
from app.domain.testing.engine import evaluate
from app.main import app
from app.models.user import Role
from app.schemas.api_definition import SendResult, SentRequest
from app.schemas.assertion import Assertion

BODY = {
    "status": "ok",
    "count": 3,
    "active": True,
    "missing_value": None,
    "data": {"user": {"id": 42, "email": "ayse@example.com", "tags": ["admin", "beta"]}},
    "items": [{"id": 1}, {"id": 2}, {"id": 3}],
    "alan adı": "boşluklu",
}


def response(status_code: int = 200, elapsed_ms: float = 120.0, body=BODY) -> SendResult:
    text = json.dumps(body) if body is not None else "merhaba"
    return SendResult(
        ok=True,
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        headers={"Content-Type": "application/json; charset=utf-8", "X-Request-Id": "abc"},
        body=text,
        body_json=body,
        request=SentRequest(method="GET", url="https://x", headers={}),
    )


def rule(type_: str, operator: str, expected=None, target=None) -> dict:
    return {"type": type_, "operator": operator, "expected": expected, "target": target}


def check(rule_data: dict, result: SendResult | None = None) -> bool:
    [outcome] = evaluate([rule_data], result or response())
    return outcome.passed


# --- JSONPath ---


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("$", BODY),
        ("$.status", "ok"),
        ("status", "ok"),
        ("$.data.user.id", 42),
        ("$.items[0].id", 1),
        ("$.items[-1].id", 3),
        ("$.data.user.tags[1]", "beta"),
        ("$['alan adı']", "boşluklu"),
        ("$.missing_value", None),
    ],
)
def test_jsonpath_extract(path, expected) -> None:
    assert jsonpath.extract(BODY, path) == expected


@pytest.mark.parametrize("path", ["$.yok", "$.items[9]", "$.status.alt", "$.data[0]"])
def test_jsonpath_missing(path) -> None:
    assert jsonpath.extract(BODY, path) is jsonpath.MISSING


@pytest.mark.parametrize("path", ["$..a", "$.items[*]", "$.a b", ""])
def test_jsonpath_invalid(path) -> None:
    with pytest.raises(ValueError):
        jsonpath.parse(path)


# --- Durum kodu (ATOP-32) ---


@pytest.mark.parametrize(
    ("operator", "expected", "code", "passed"),
    [
        ("equals", "200", 200, True),
        ("equals", "200", 404, False),
        ("not_equals", "500", 200, True),
        ("in_range", "2xx", 204, True),
        ("in_range", "2xx", 301, False),
        ("in_range", "400-499", 404, True),
        ("in_list", "200, 201,204", 201, True),
        ("in_list", "200,201", 202, False),
    ],
)
def test_status_code(operator, expected, code, passed) -> None:
    assert check(rule("status_code", operator, expected), response(status_code=code)) is passed


# --- Yanıt süresi (ATOP-33) ---


def test_response_time() -> None:
    assert check(rule("response_time", "less_than", "500"), response(elapsed_ms=120)) is True
    assert check(rule("response_time", "less_than", "100"), response(elapsed_ms=120)) is False


# --- JSON alan ve değer (ATOP-34) ---


@pytest.mark.parametrize(
    ("target", "operator", "expected", "passed"),
    [
        ("$.status", "exists", None, True),
        ("$.yok", "exists", None, False),
        ("$.yok", "not_exists", None, True),
        ("$.missing_value", "exists", None, True),  # alan var, değeri null
        ("$.status", "equals", "ok", True),
        ("$.status", "equals", '"ok"', True),
        ("$.status", "equals", "OK", False),
        ("$.count", "equals", "3", True),
        ("$.active", "equals", "true", True),
        ("$.active", "equals", "1", False),  # true ile 1 aynı sayılmaz
        ("$.missing_value", "equals", "null", True),
        ("$.status", "not_equals", "error", True),
        ("$.data.user.email", "contains", "@example.com", True),
        ("$.data.user.tags", "contains", "admin", True),
        ("$.data.user.tags", "contains", "root", False),
        ("$.data.user", "contains", "email", True),
        ("$.data.user.email", "matches", r"^[\w.]+@[\w.]+$", True),
        ("$.data.user.id", "matches", r"^\d+$", True),
        ("$.status", "type_is", "string", True),
        ("$.count", "type_is", "number", True),
        ("$.active", "type_is", "boolean", True),
        ("$.items", "type_is", "array", True),
        ("$.data", "type_is", "object", True),
        ("$.missing_value", "type_is", "null", True),
        ("$.active", "type_is", "number", False),
        ("$.count", "greater_than", "2", True),
        ("$.count", "less_than", "3", False),
        ("$.status", "greater_than", "1", False),  # metin sayı değil
    ],
)
def test_json_path_rules(target, operator, expected, passed) -> None:
    assert check(rule("json_path", operator, expected, target)) is passed


def test_json_rule_on_non_json_body_fails_with_message() -> None:
    [outcome] = evaluate([rule("json_path", "exists", target="$.a")], response(body=None))
    assert outcome.passed is False
    assert "JSON değil" in outcome.message


# --- Header ---


def test_header_rules_are_case_insensitive() -> None:
    assert check(rule("header", "exists", target="content-type")) is True
    assert check(rule("header", "contains", "application/json", "Content-Type")) is True
    assert check(rule("header", "equals", "abc", "x-request-id")) is True
    assert check(rule("header", "not_exists", target="X-Yok")) is True


# --- Genel davranış ---


def test_result_contains_actual_value_and_message() -> None:
    [outcome] = evaluate([rule("status_code", "equals", "201")], response(status_code=200))
    assert outcome.passed is False
    assert outcome.actual == "200"
    assert "201" in outcome.message and "200" in outcome.message


def test_disabled_rules_are_skipped() -> None:
    rules = [rule("status_code", "equals", "500") | {"enabled": False}]
    assert evaluate(rules, response()) == []


def test_all_rules_fail_when_no_response() -> None:
    failed = SendResult(
        ok=False,
        elapsed_ms=0,
        error="bağlanılamadı",
        request=SentRequest(method="GET", url="https://x", headers={}),
    )
    [outcome] = evaluate([rule("status_code", "equals", "200")], failed)
    assert outcome.passed is False
    assert outcome.message == "Cevap alınamadı"


def test_variables_in_rules_are_resolved() -> None:
    rules = [rule("json_path", "equals", "{{beklenen}}", "$.status")]
    assert evaluate(rules, response(), {"beklenen": "ok"})[0].passed is True
    missing = evaluate(rules, response(), {})[0]
    assert missing.passed is False
    assert "beklenen" in missing.message


# --- Kural doğrulama (kaydederken 422) ---


@pytest.mark.parametrize(
    "data",
    [
        rule("status_code", "contains", "200"),  # bu tipte olmayan operatör
        rule("status_code", "equals", "abc"),
        rule("status_code", "equals", "999"),
        rule("status_code", "in_range", "2x"),
        rule("response_time", "less_than", "-5"),
        rule("json_path", "equals", "ok"),  # hedef yok
        rule("json_path", "equals", None, "$.a"),  # beklenen yok
        rule("json_path", "type_is", "tarih", "$.a"),
        rule("json_path", "matches", "([a-z", "$.a"),
        rule("json_path", "exists", None, "$..a"),
        rule("header", "exists"),
    ],
)
def test_invalid_rules_are_rejected(data) -> None:
    with pytest.raises(ValueError):
        Assertion.model_validate(data)


def test_valid_rule_is_normalized() -> None:
    parsed = Assertion.model_validate(rule("json_path", "exists", "gereksiz", "  $.a  "))
    assert parsed.target == "$.a"
    assert parsed.expected is None


# --- Uçtan uca: /run ---


@pytest.fixture
def tester(make_user, login) -> dict[str, str]:
    make_user("tester@apitest.com", Role.TESTER)
    return login("tester@apitest.com")


@pytest.fixture
def fake_server() -> Iterator[None]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "checks": {"database": "ok"}})

    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(handler)
    yield
    app.dependency_overrides.pop(get_http_transport, None)


def create_api(api: TestClient, headers, assertions) -> int:
    response_ = api.post(
        "/api/apis",
        json={"name": "Sağlık", "url": "https://x.com/health", "assertions": assertions},
        headers=headers,
    )
    assert response_.status_code == 201, response_.text
    return response_.json()["id"]


def test_assertions_are_saved_with_api(api: TestClient, tester) -> None:
    rules = [rule("status_code", "equals", "200"), rule("json_path", "exists", target="$.a")]
    api_id = create_api(api, tester, rules)

    saved = api.get(f"/api/apis/{api_id}", headers=tester).json()["assertions"]
    assert [item["type"] for item in saved] == ["status_code", "json_path"]

    response_ = api.patch(
        f"/api/apis/{api_id}", json={"assertions": [rule("status_code", "x", "1")]}, headers=tester
    )
    assert response_.status_code == 422


def test_run_passes_and_is_recorded(api: TestClient, tester, fake_server) -> None:
    api_id = create_api(
        api,
        tester,
        [
            rule("status_code", "equals", "200"),
            rule("response_time", "less_than", "5000"),
            rule("json_path", "equals", "ok", "$.checks.database"),
        ],
    )

    run = api.post(f"/api/apis/{api_id}/run", headers=tester)
    assert run.status_code == 200, run.text
    data = run.json()
    assert data["status"] == "passed"
    assert data["passed_count"] == 3
    assert data["failed_count"] == 0
    assert data["response"]["status_code"] == 200
    assert '"database"' in data["response"]["body"]

    # Kayıt veritabanına yazıldı ve listelenebiliyor
    runs = api.get(f"/api/runs?api_id={api_id}", headers=tester).json()
    assert [item["id"] for item in runs] == [data["id"]]
    detail = api.get(f"/api/runs/{data['id']}", headers=tester).json()
    assert len(detail["assertion_results"]) == 3


def test_run_with_failing_rule(api: TestClient, tester, fake_server) -> None:
    api_id = create_api(
        api,
        tester,
        [rule("status_code", "equals", "200"), rule("json_path", "equals", "error", "$.status")],
    )
    data = api.post(f"/api/apis/{api_id}/run", headers=tester).json()

    assert data["status"] == "failed"
    assert (data["passed_count"], data["failed_count"]) == (1, 1)
    failed = data["assertion_results"][1]
    assert failed["passed"] is False
    assert failed["actual"] == "ok"


def test_run_without_response_is_error(api: TestClient, tester) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kapalı", request=request)

    app.dependency_overrides[get_http_transport] = lambda: httpx.MockTransport(handler)
    try:
        api_id = create_api(api, tester, [rule("status_code", "equals", "200")])
        data = api.post(f"/api/apis/{api_id}/run", headers=tester).json()
    finally:
        app.dependency_overrides.pop(get_http_transport, None)

    assert data["status"] == "error"
    assert data["response"] is None
    assert "bağlanılamadı" in data["error"]


def test_viewer_can_see_runs_but_not_run(
    api: TestClient, tester, make_user, login, fake_server
) -> None:
    api_id = create_api(api, tester, [])
    api.post(f"/api/apis/{api_id}/run", headers=tester)

    make_user("viewer@apitest.com", Role.VIEWER)
    viewer = login("viewer@apitest.com")
    assert api.post(f"/api/apis/{api_id}/run", headers=viewer).status_code == 403
    assert len(api.get("/api/runs", headers=viewer).json()) == 1
    assert api.get("/api/runs/999", headers=viewer).status_code == 404
