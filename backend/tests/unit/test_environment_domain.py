"""Ortam domain kuralları: gizli değişkenler, MASK ve çözme; veritabanı olmadan."""

import pytest

from app.domain.environments import Environment, EnvironmentVariable, VariableInput
from app.domain.errors import InvalidInput, SecretUnreadable
from app.domain.secrets import MASK


def encrypt(plain: str) -> str:
    return f"enc:{plain}"


def decrypt(token: str) -> str:
    if not token.startswith("enc:"):
        raise SecretUnreadable("çözülemedi")
    return token.removeprefix("enc:")


def make_environment() -> Environment:
    environment = Environment(name="Stage")
    environment.replace_variables(
        [
            VariableInput("base_url", "https://stage.example.com"),
            VariableInput("token", "gizli-123", is_secret=True),
        ],
        encrypt,
    )
    return environment


def test_secret_values_are_encrypted_plain_values_are_not() -> None:
    stored = {v.key: v.value for v in make_environment().variables}
    assert stored == {"base_url": "https://stage.example.com", "token": "enc:gizli-123"}


def test_secret_value_is_masked_for_display() -> None:
    shown = {v.key: v.display_value for v in make_environment().variables}
    assert shown == {"base_url": "https://stage.example.com", "token": MASK}


def test_empty_secret_is_not_masked() -> None:
    assert EnvironmentVariable(key="x", value="", is_secret=True).display_value == ""


def test_mask_keeps_the_stored_secret() -> None:
    environment = make_environment()

    environment.replace_variables([VariableInput("token", MASK, is_secret=True)], encrypt)

    assert [(v.key, v.value) for v in environment.variables] == [("token", "enc:gizli-123")]


def test_mask_without_stored_secret_is_rejected() -> None:
    environment = make_environment()

    with pytest.raises(InvalidInput, match="'yeni'"):
        environment.replace_variables([VariableInput("yeni", MASK, is_secret=True)], encrypt)


def test_mask_for_previously_plain_variable_is_rejected() -> None:
    environment = make_environment()

    with pytest.raises(InvalidInput):
        environment.replace_variables([VariableInput("base_url", MASK, is_secret=True)], encrypt)


def test_existing_rows_are_updated_not_recreated() -> None:
    environment = make_environment()
    old_row = environment.variables[0]

    environment.replace_variables([VariableInput("base_url", "https://yeni.example.com")], encrypt)

    assert environment.variables == [old_row]
    assert old_row.value == "https://yeni.example.com"


def test_resolve_returns_plain_values_and_secret_list() -> None:
    values, secrets = make_environment().resolve_variables(decrypt)

    assert values == {"base_url": "https://stage.example.com", "token": "gizli-123"}
    assert secrets == ["gizli-123"]


def test_resolve_names_the_unreadable_variable() -> None:
    environment = Environment(
        name="Bozuk", variables=[EnvironmentVariable(key="token", value="xx", is_secret=True)]
    )

    with pytest.raises(SecretUnreadable, match="'token' çözülemedi"):
        environment.resolve_variables(decrypt)
