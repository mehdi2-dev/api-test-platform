"""Tekil gönderme ve test çalıştırma use case'leri: sahte gönderici ve bellek içi depoyla.

Gerçek ağ, httpx veya veritabanı yok: ApiSender portuna sahte bir gönderici takılı.
"""

import json

import pytest

from app.application.use_cases.api_definitions import PrepareApiRequest
from app.application.use_cases.testing import RunApiTest, SendApiRequest
from app.domain.api_definitions import ApiDefinition, AuthType
from app.domain.environments import Environment, VariableInput
from app.domain.secrets import MASK
from app.domain.testing.runs import ApiTestRun, RunStatus, SendOutcome, SentRequest
from app.domain.users import Role, User
from tests.fakes import (
    FakeApiSender,
    FakeCipher,
    InMemoryApiDefinitionRepository,
    InMemoryApiTestRunRepository,
    InMemoryEnvironmentRepository,
)

TESTER = User(email="t@apitest.com", full_name="T", hashed_password="x", role=Role.TESTER, id=7)
BODY = {"status": "ok", "access_token": "cok-gizli", "echo": "stage-token-123"}


def outcome(**changes) -> SendOutcome:
    data = {
        "ok": True,
        "status_code": 200,
        "elapsed_ms": 42.0,
        "headers": {"Content-Type": "application/json", "Set-Cookie": "oturum=abc"},
        "body": json.dumps(BODY),
        "body_json": BODY,
        "request": SentRequest(method="GET", url="https://stage.x.com/me", headers={}),
        "environment": "Stage",
    }
    return SendOutcome(**{**data, **changes})


@pytest.fixture
def apis() -> InMemoryApiDefinitionRepository:
    repo = InMemoryApiDefinitionRepository()
    api = ApiDefinition(
        name="Profil",
        url="{{base_url}}/me",
        assertions=[
            {"type": "status_code", "operator": "equals", "expected": "200"},
            {"type": "json_path", "target": "$.status", "operator": "equals", "expected": "ok"},
        ],
    )
    api.change_auth(
        AuthType.BEARER,
        {"token": "abc"},
        encrypt=FakeCipher().encrypt,
        decrypt=FakeCipher().decrypt,
    )
    repo.save(api)
    return repo


@pytest.fixture
def environments() -> InMemoryEnvironmentRepository:
    repo = InMemoryEnvironmentRepository()
    stage = Environment(name="Stage")
    stage.replace_variables(
        [
            VariableInput("base_url", "https://stage.x.com"),
            VariableInput("token", "stage-token-123", is_secret=True),
        ],
        FakeCipher().encrypt,
    )
    repo.save(stage)
    return repo


@pytest.fixture
def prepare(apis, environments) -> PrepareApiRequest:
    return PrepareApiRequest(apis, environments, FakeCipher())


def test_sender_gets_decrypted_auth_and_resolved_variables(prepare) -> None:
    sender = FakeApiSender(outcome())

    SendApiRequest(prepare, sender)(1, environment_id=1)

    [call] = sender.calls
    assert call["auth"] == {"token": "abc"}
    assert call["variables"]["base_url"] == "https://stage.x.com"
    assert call["secrets"] == ["stage-token-123"]
    assert call["environment_name"] == "Stage"


def test_send_masks_secrets_and_sensitive_fields_for_display(prepare) -> None:
    shown = SendApiRequest(prepare, FakeApiSender(outcome()))(1, environment_id=1)

    assert shown.body_json == {"status": "ok", "access_token": MASK, "echo": MASK}
    assert shown.headers["Set-Cookie"] == MASK


def test_run_evaluates_rules_on_the_real_response_and_saves_masked_record(prepare) -> None:
    runs = InMemoryApiTestRunRepository()

    run = RunApiTest(prepare, FakeApiSender(outcome()), runs)(1, user=TESTER, environment_id=1)

    assert run.id is not None and runs.items == [run]
    assert (run.status, run.passed_count, run.failed_count) == (RunStatus.PASSED, 2, 0)
    assert run.triggered_by_id == 7 and run.environment_name == "Stage"
    stored_body = json.loads(run.response["body"])
    assert stored_body["access_token"] == MASK and stored_body["echo"] == MASK


def test_failing_rule_marks_run_failed(prepare) -> None:
    run = RunApiTest(
        prepare, FakeApiSender(outcome(status_code=500)), InMemoryApiTestRunRepository()
    )(1, user=TESTER)
    assert (run.status, run.passed_count, run.failed_count) == (RunStatus.FAILED, 1, 1)


def test_no_response_is_an_error_and_keeps_no_body() -> None:
    api = ApiDefinition(name="X", url="https://x.com", id=3)
    failed = outcome(ok=False, status_code=None, error="Sunucuya bağlanılamadı", body="")

    run = ApiTestRun.record(api=api, outcome=failed, results=[], triggered_by_id=None)

    assert (run.status, run.response, run.error) == (
        RunStatus.ERROR,
        None,
        "Sunucuya bağlanılamadı",
    )
    assert run.request == {"method": "GET", "url": "https://stage.x.com/me", "headers": {}}
