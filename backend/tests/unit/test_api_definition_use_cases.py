"""API tanımı use case'leri, bellek içi adaptörlerle."""

import pytest

from app.application.use_cases.api_definitions import (
    CreateApiDefinition,
    DeleteApiDefinition,
    GetApiDefinition,
    ListApiDefinitions,
    PrepareApiRequest,
    UpdateApiDefinition,
)
from app.domain.api_definitions import AuthType, BodyType, HttpMethod
from app.domain.environments import Environment, VariableInput
from app.domain.errors import NotFound, ProductionConfirmationRequired
from app.domain.secrets import MASK
from app.domain.users import Role, User
from tests.fakes import FakeCipher, InMemoryApiDefinitionRepository, InMemoryEnvironmentRepository

TESTER = User(email="t@apitest.com", full_name="T", hashed_password="x", role=Role.TESTER, id=7)


@pytest.fixture
def apis() -> InMemoryApiDefinitionRepository:
    return InMemoryApiDefinitionRepository()


@pytest.fixture
def environments() -> InMemoryEnvironmentRepository:
    repo = InMemoryEnvironmentRepository()
    for name, is_production in [("Stage", False), ("Prod", True)]:
        environment = Environment(name=name, is_production=is_production)
        environment.replace_variables(
            [
                VariableInput("base_url", f"https://{name.lower()}.x.com"),
                VariableInput("token", f"{name}-gizli", is_secret=True),
            ],
            FakeCipher().encrypt,
        )
        repo.save(environment)
    return repo


def create(apis, name: str = "Kullanıcılar", method: HttpMethod = HttpMethod.GET):
    return CreateApiDefinition(apis, FakeCipher())(
        created_by=TESTER,
        name=name,
        description=None,
        method=method,
        url="{{base_url}}/users",
        headers=[],
        query_params=[],
        body_type=BodyType.NONE,
        body=None,
        assertions=[],
        auth_type=AuthType.BEARER,
        auth_fields={"token": "abc"},
    )


def test_create_records_owner_and_encrypts_auth(apis) -> None:
    api = create(apis)

    assert api.id is not None and api.created_by_id == 7
    assert api.auth_config_encrypted == 'enc:{"token": "abc"}'


def test_list_searches_by_name(apis) -> None:
    create(apis, "Kullanıcılar")
    create(apis, "Siparişler")

    assert [a.name for a in ListApiDefinitions(apis)("sipar")] == ["Siparişler"]
    assert len(ListApiDefinitions(apis)()) == 2


def test_update_keeps_masked_token_and_replaces_assertions(apis) -> None:
    api = create(apis)
    rule = {"type": "status_code", "operator": "equals", "expected": 200}

    UpdateApiDefinition(apis, FakeCipher())(
        api.id,
        changes={"name": "Yeni ad"},
        assertions=[rule],
        auth_type=AuthType.BEARER,
        auth_fields={"token": MASK},
    )

    assert api.name == "Yeni ad"
    assert api.assertions == [rule]
    assert api.stored_auth(FakeCipher().decrypt) == {"token": "abc"}


def test_delete_then_not_found(apis) -> None:
    api = create(apis)

    DeleteApiDefinition(apis)(api.id)

    with pytest.raises(NotFound, match="API tanımı bulunamadı"):
        GetApiDefinition(apis)(api.id)


def test_prepare_without_environment(apis, environments) -> None:
    prepared = PrepareApiRequest(apis, environments, FakeCipher())(create(apis).id)

    assert prepared.auth == {"token": "abc"}
    assert (prepared.variables, prepared.secrets, prepared.environment_name) == ({}, [], None)


def test_prepare_resolves_environment_variables(apis, environments) -> None:
    prepared = PrepareApiRequest(apis, environments, FakeCipher())(
        create(apis).id, environment_id=1
    )

    assert prepared.environment_name == "Stage"
    assert prepared.variables == {"base_url": "https://stage.x.com", "token": "Stage-gizli"}
    assert prepared.secrets == ["Stage-gizli"]


def test_prepare_guards_production_for_mutating_requests(apis, environments) -> None:
    prepare = PrepareApiRequest(apis, environments, FakeCipher())
    post = create(apis, "Sipariş oluştur", HttpMethod.POST)

    with pytest.raises(ProductionConfirmationRequired):
        prepare(post.id, environment_id=2)
    assert prepare(post.id, environment_id=2, confirm_production=True).environment_name == "Prod"


def test_prepare_unknown_environment(apis, environments) -> None:
    with pytest.raises(NotFound, match="Ortam bulunamadı"):
        PrepareApiRequest(apis, environments, FakeCipher())(create(apis).id, environment_id=99)
