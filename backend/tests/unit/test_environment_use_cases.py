"""Ortam use case'leri, bellek içi adaptörlerle."""

import pytest

from app.application.use_cases.environments import (
    CreateEnvironment,
    DeleteEnvironment,
    GetEnvironment,
    ListEnvironments,
    UpdateEnvironment,
)
from app.domain.environments import VariableInput
from app.domain.errors import Conflict, NotFound
from tests.fakes import FakeCipher, InMemoryEnvironmentRepository


@pytest.fixture
def environments() -> InMemoryEnvironmentRepository:
    return InMemoryEnvironmentRepository()


@pytest.fixture
def create(environments) -> CreateEnvironment:
    return CreateEnvironment(environments, FakeCipher())


def test_create_encrypts_secrets_through_the_cipher_port(create) -> None:
    environment = create(
        name="Stage",
        description=None,
        is_production=False,
        variables=[VariableInput("token", "gizli", is_secret=True)],
    )

    assert environment.id is not None
    assert environment.variables[0].value == "enc:gizli"


def test_names_must_be_unique(create) -> None:
    create(name="Stage", description=None, is_production=False, variables=[])

    with pytest.raises(Conflict, match="'Stage'"):
        create(name="Stage", description=None, is_production=True, variables=[])


def test_list_puts_production_last(create, environments) -> None:
    create(name="Prod", description=None, is_production=True, variables=[])
    create(name="Dev", description=None, is_production=False, variables=[])

    assert [e.name for e in ListEnvironments(environments)()] == ["Dev", "Prod"]


def test_update_keeps_fields_that_are_not_given(create, environments) -> None:
    environment = create(name="Stage", description="Test", is_production=False, variables=[])

    UpdateEnvironment(environments, FakeCipher())(environment.id, is_production=True)

    assert (environment.name, environment.description, environment.is_production) == (
        "Stage",
        "Test",
        True,
    )


def test_update_can_clear_description(create, environments) -> None:
    environment = create(name="Stage", description="Test", is_production=False, variables=[])

    UpdateEnvironment(environments, FakeCipher())(environment.id, description=None)

    assert environment.description is None


def test_renaming_to_own_name_is_allowed_but_not_to_another(create, environments) -> None:
    stage = create(name="Stage", description=None, is_production=False, variables=[])
    create(name="Dev", description=None, is_production=False, variables=[])
    update = UpdateEnvironment(environments, FakeCipher())

    update(stage.id, name="Stage")
    with pytest.raises(Conflict):
        update(stage.id, name="Dev")


def test_delete_and_not_found(create, environments) -> None:
    environment = create(name="Stage", description=None, is_production=False, variables=[])

    DeleteEnvironment(environments)(environment.id)

    with pytest.raises(NotFound, match="Ortam bulunamadı"):
        GetEnvironment(environments)(environment.id)
