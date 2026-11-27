"""Koleksiyon yönetimi, içe/dışa aktarma ve kuyruğa alma use case'leri; bellek içi depolarla."""

import json

import pytest

from app.adapters.outbound.queue import CallableRunQueue
from app.application.errors import QueueUnavailable
from app.application.use_cases.collection_runs import PrepareCollectionRun
from app.application.use_cases.collections import (
    QUEUE_ERROR,
    CreateCollection,
    ExportCollection,
    ImportCollection,
    ImportedApi,
    ImportedStep,
    QueueCollectionRun,
    UpdateCollection,
)
from app.domain.api_definitions import ApiDefinition, AuthType, BodyType, HttpMethod
from app.domain.collections import StepInput
from app.domain.errors import Conflict, InvalidInput
from app.domain.testing.runs import RunStatus
from app.domain.users import Role, User
from tests.fakes import (
    FakeCipher,
    InMemoryApiDefinitionRepository,
    InMemoryCollectionRepository,
    InMemoryCollectionRunRepository,
    InMemoryEnvironmentRepository,
)

TESTER = User(email="t@apitest.com", full_name="T", hashed_password="x", role=Role.TESTER, id=7)
TOKEN = {"variable": "token", "source": "json_path", "path": "$.access_token", "secret": True}


@pytest.fixture
def apis() -> InMemoryApiDefinitionRepository:
    repo = InMemoryApiDefinitionRepository()
    login = ApiDefinition(name="Giriş", url="{{base_url}}/login", method=HttpMethod.POST)
    login.change_auth(
        AuthType.BEARER,
        {"token": "gizli"},
        encrypt=FakeCipher().encrypt,
        decrypt=FakeCipher().decrypt,
    )
    repo.save(login)
    repo.save(ApiDefinition(name="Profil", url="{{base_url}}/me?id={{user_id}}"))
    return repo


@pytest.fixture
def collections() -> InMemoryCollectionRepository:
    return InMemoryCollectionRepository()


def create(collections, apis, name="Senaryo", steps=None):
    steps = steps if steps is not None else [StepInput(1, extractions=[TOKEN]), StepInput(2)]
    collection = CreateCollection(collections, apis)(
        created_by=TESTER, name=name, description=None, stop_on_failure=False, steps=steps
    )
    for item in collection.items:  # bellek içi depoda ilişkiyi elle bağlıyoruz
        item.api = apis.get(item.api_definition_id)
    return collection


def test_create_orders_steps_and_records_owner(collections, apis) -> None:
    collection = create(collections, apis)

    assert [(i.position, i.api_definition_id) for i in collection.items] == [(0, 1), (1, 2)]
    assert collection.created_by_id == 7


def test_names_are_unique_and_apis_must_exist(collections, apis) -> None:
    create(collections, apis)

    with pytest.raises(Conflict, match="'Senaryo'"):
        create(collections, apis)
    with pytest.raises(InvalidInput, match="API tanımı bulunamadı: 8, 9"):
        create(collections, apis, "Yeni", [StepInput(9), StepInput(8), StepInput(1)])


def test_update_replaces_steps_and_keeps_other_fields(collections, apis) -> None:
    collection = create(collections, apis)

    UpdateCollection(collections, apis)(collection.id, stop_on_failure=True, steps=[StepInput(2)])

    assert [i.api_definition_id for i in collection.items] == [2]
    assert (collection.name, collection.stop_on_failure) == ("Senaryo", True)


def test_export_hides_secrets_and_lists_required_variables(collections, apis) -> None:
    collection = create(collections, apis)

    exported = ExportCollection(collections, FakeCipher())(collection.id)

    assert exported.apis[0]["auth"] == {"type": "bearer", "token": "{{token}}"}
    assert "gizli" not in json.dumps(exported.apis)
    assert exported.steps[0] == {"api": 0, "enabled": True, "extractions": [TOKEN]}
    # token adımda cevaptan alındığı için listede yok
    assert exported.required_variables == ["base_url", "user_id"]


def test_import_creates_apis_and_renames_on_conflict(collections, apis) -> None:
    create(collections, apis)
    imported_api = ImportedApi(
        name="Giriş",
        description=None,
        method=HttpMethod.POST,
        url="{{base_url}}/login",
        headers=[],
        query_params=[],
        body_type=BodyType.NONE,
        body=None,
        assertions=[],
        auth_type=AuthType.BEARER,
        auth_fields={"token": "{{token}}"},
    )

    collection, created = ImportCollection(collections, apis, FakeCipher())(
        name="Senaryo",
        description=None,
        stop_on_failure=False,
        apis=[imported_api],
        steps=[ImportedStep(api=0), ImportedStep(api=0, enabled=False)],
        user_id=None,
    )

    assert (collection.name, created) == ("Senaryo (2)", 1)
    assert [i.api_definition_id for i in collection.items] == [3, 3]
    assert apis.get(3).stored_auth(FakeCipher().decrypt) == {"token": "{{token}}"}


def test_queue_failure_marks_run_failed(collections, apis) -> None:
    collection = create(collections, apis)
    runs = InMemoryCollectionRunRepository()

    def broken_queue(*_):
        raise ConnectionError("Redis yok")

    queue = QueueCollectionRun(
        collections,
        InMemoryEnvironmentRepository(),
        PrepareCollectionRun(InMemoryEnvironmentRepository(), FakeCipher()),
        runs,
        CallableRunQueue(broken_queue),
    )
    with pytest.raises(QueueUnavailable):
        queue(collection.id, user=TESTER)

    [run] = runs.items.values()
    assert (run.state, run.status, run.error) == ("completed", RunStatus.ERROR, QUEUE_ERROR)


def test_collection_without_enabled_steps_cannot_run(collections, apis) -> None:
    collection = create(collections, apis, steps=[StepInput(1, enabled=False)])
    queue = QueueCollectionRun(
        collections,
        InMemoryEnvironmentRepository(),
        PrepareCollectionRun(InMemoryEnvironmentRepository(), FakeCipher()),
        InMemoryCollectionRunRepository(),
        None,
    )

    with pytest.raises(InvalidInput, match="etkin adım yok"):
        queue(collection.id, user=TESTER)
