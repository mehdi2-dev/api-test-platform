"""Koleksiyon çalıştırma (domain + use case): sahte gönderici ve bellek içi depolarla.

Ağ, Celery veya veritabanı yok; adımların sırası, değişken aktarımı, "hata olursa dur"
ve Production kuralı doğrudan test edilir.
"""

import json

import pytest

from app.application.use_cases.collection_runs import (
    ExecuteQueuedRun,
    PrepareCollectionRun,
    RunCollection,
    RunContext,
)
from app.domain.api_definitions import ApiDefinition, HttpMethod
from app.domain.collections import (
    Collection,
    CollectionItem,
    CollectionRun,
    Extraction,
    RunState,
    extract_value,
)
from app.domain.environments import Environment
from app.domain.errors import ProductionConfirmationRequired
from app.domain.secrets import MASK
from app.domain.testing.runs import RunStatus, SendOutcome, SentRequest
from tests.fakes import (
    FakeApiSender,
    FakeCipher,
    InMemoryApiTestRunRepository,
    InMemoryCollectionRepository,
    InMemoryCollectionRunRepository,
    InMemoryEnvironmentRepository,
    RecordingNotifier,
)

STATUS_200 = [{"type": "status_code", "operator": "equals", "expected": "200"}]


def outcome(status_code: int = 200, body: dict | None = None) -> SendOutcome:
    body = body if body is not None else {"ok": True}
    return SendOutcome(
        ok=True,
        status_code=status_code,
        elapsed_ms=10.0,
        body=json.dumps(body),
        body_json=body,
        request=SentRequest(method="GET", url="https://x"),
    )


def step(position: int, api: ApiDefinition | None, extractions=None, enabled=True):
    item = CollectionItem(
        api_definition_id=api.id if api else 99,
        position=position,
        enabled=enabled,
        extractions=extractions or [],
    )
    item.api = api
    return item


def api(api_id: int, name: str, method: HttpMethod = HttpMethod.GET) -> ApiDefinition:
    return ApiDefinition(
        id=api_id, name=name, url="https://x", method=method, assertions=STATUS_200
    )


LOGIN = api(1, "Giriş", HttpMethod.POST)
PROFILE = api(2, "Profil")
TOKEN = [{"variable": "token", "source": "json_path", "path": "$.access_token", "secret": True}]


@pytest.fixture
def runs() -> InMemoryCollectionRunRepository:
    return InMemoryCollectionRunRepository()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


def runner(sender, runs, notifier) -> RunCollection:
    return RunCollection(sender, InMemoryApiTestRunRepository(), runs, FakeCipher(), notifier)


# --- Domain ---


def test_extract_value_from_json_header_and_status() -> None:
    response = outcome(201, {"data": {"id": 7}})
    response.headers = {"Location": "/users/7"}

    assert extract_value(Extraction("id", "json_path", "$.data.id"), response) == "7"
    assert extract_value(Extraction("loc", "header", "location"), response) == "/users/7"
    assert extract_value(Extraction("code", "status_code"), response) == "201"
    assert extract_value(Extraction("yok", "json_path", "$.yok"), response) is None


def test_production_guard_lists_risky_steps() -> None:
    collection = Collection(name="Senaryo", items=[step(0, LOGIN), step(1, PROFILE)])
    prod = Environment(name="Prod", is_production=True)

    with pytest.raises(ProductionConfirmationRequired, match="POST Giriş"):
        collection.ensure_production_confirmed(prod, confirmed=False)
    collection.ensure_production_confirmed(prod, confirmed=True)
    collection.ensure_production_confirmed(Environment(name="Stage"), confirmed=False)


def test_run_result_counts() -> None:
    run = CollectionRun(collection_name="X")
    run.fail("Koleksiyon silinmiş")
    assert (run.state, run.status, run.error) == (
        "completed",
        RunStatus.ERROR,
        "Koleksiyon silinmiş",
    )


# --- Use case ---


def test_token_from_first_step_is_passed_to_the_next(runs, notifier) -> None:
    sender = FakeApiSender(outcome(body={"access_token": "abc123"}), outcome())
    collection = Collection(name="Senaryo", items=[step(0, LOGIN, TOKEN), step(1, PROFILE)], id=5)

    run = runner(sender, runs, notifier)(collection, RunContext(), user_id=3)

    assert sender.calls[1]["variables"]["token"] == "abc123"
    assert "abc123" in sender.calls[1]["secrets"]
    assert run.steps[0]["extracted"] == [{"variable": "token", "found": True, "value": MASK}]
    assert (run.status, run.passed_steps, run.state) == (RunStatus.PASSED, 2, "completed")
    assert notifier.notified == [run]


def test_missing_value_fails_the_step(runs, notifier) -> None:
    sender = FakeApiSender(outcome(body={"baska": 1}), outcome())
    collection = Collection(name="Senaryo", items=[step(0, LOGIN, TOKEN), step(1, PROFILE)])

    run = runner(sender, runs, notifier)(collection, RunContext(), user_id=None)

    assert [s["status"] for s in run.steps] == ["failed", "passed"]
    assert run.status == RunStatus.FAILED


def test_stop_on_failure_skips_the_rest(runs, notifier) -> None:
    sender = FakeApiSender(outcome(500), outcome())
    collection = Collection(
        name="Senaryo", stop_on_failure=True, items=[step(0, LOGIN), step(1, PROFILE)]
    )

    run = runner(sender, runs, notifier)(collection, RunContext(), user_id=None)

    assert [s["status"] for s in run.steps] == ["failed", "skipped"]
    assert len(sender.calls) == 1
    assert (run.failed_steps, run.skipped_steps) == (1, 1)


def test_disabled_steps_and_deleted_apis(runs, notifier) -> None:
    collection = Collection(
        name="Senaryo", items=[step(0, PROFILE, enabled=False), step(1, None), step(2, PROFILE)]
    )

    run = runner(FakeApiSender(outcome()), runs, notifier)(collection, RunContext(), None)

    assert [(s["position"], s["status"]) for s in run.steps] == [(1, "error"), (2, "passed")]
    assert run.status == RunStatus.ERROR


def test_prepare_resolves_environment_and_guards_production() -> None:
    environments = InMemoryEnvironmentRepository()
    environments.save(Environment(name="Prod", is_production=True))
    prepare = PrepareCollectionRun(environments, FakeCipher())
    collection = Collection(name="Senaryo", items=[step(0, LOGIN)])

    assert prepare(collection, None, False) == RunContext()
    with pytest.raises(ProductionConfirmationRequired):
        prepare(collection, 1, False)
    assert prepare(collection, 1, True).environment_name == "Prod"


def test_queued_run_fails_cleanly_when_preparation_fails(runs, notifier) -> None:
    environments = InMemoryEnvironmentRepository()
    environments.save(Environment(name="Prod", is_production=True))
    collections = InMemoryCollectionRepository()
    collection = Collection(name="Senaryo", items=[step(0, LOGIN)])
    collections.save(collection)
    queued = CollectionRun.new(collection, RunState.QUEUED)
    runs.save(queued)
    execute = ExecuteQueuedRun(
        collections,
        runs,
        PrepareCollectionRun(environments, FakeCipher()),
        runner(FakeApiSender(outcome()), runs, notifier),
        notifier,
    )

    result = execute(queued.id, environment_id=1, confirm_production=False)

    assert (result.state, result.status) == ("completed", RunStatus.ERROR)
    assert "Production" in result.error
    assert notifier.notified == [result]
    assert execute(queued.id, 1, False) is result  # ikinci kez gelirse dokunulmaz
