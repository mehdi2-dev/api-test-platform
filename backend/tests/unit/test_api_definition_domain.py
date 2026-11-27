"""API tanımı domain kuralları: gizli kimlik bilgisi, güncelleme ve Production koruması."""

import json

import pytest

from app.domain.api_definitions import (
    ApiDefinition,
    AuthType,
    BodyType,
    HttpMethod,
    check_json_body,
    ensure_production_confirmed,
)
from app.domain.environments import Environment
from app.domain.errors import InvalidInput, ProductionConfirmationRequired, SecretUnreadable
from app.domain.secrets import MASK


def encrypt(plain: str) -> str:
    return f"enc:{plain}"


def decrypt(token: str) -> str:
    if not token.startswith("enc:"):
        raise SecretUnreadable("çözülemedi")
    return token.removeprefix("enc:")


def bearer_api(token: str = "gizli-token") -> ApiDefinition:
    api = ApiDefinition(name="Kullanıcılar", url="https://x.com/users")
    api.change_auth(AuthType.BEARER, {"token": token}, encrypt=encrypt, decrypt=decrypt)
    return api


def test_auth_is_stored_encrypted() -> None:
    api = bearer_api()

    assert api.auth_type == AuthType.BEARER
    assert api.auth_config_encrypted == "enc:" + json.dumps({"token": "gizli-token"})
    assert api.stored_auth(decrypt) == {"token": "gizli-token"}


def test_mask_keeps_the_stored_secret() -> None:
    api = bearer_api()

    api.change_auth(AuthType.BEARER, {"token": MASK}, encrypt=encrypt, decrypt=decrypt)

    assert api.stored_auth(decrypt) == {"token": "gizli-token"}


def test_mask_is_rejected_when_auth_type_changes() -> None:
    api = bearer_api()

    with pytest.raises(InvalidInput, match="'password'"):
        api.change_auth(
            AuthType.BASIC,
            {"username": "ali", "password": MASK},
            encrypt=encrypt,
            decrypt=decrypt,
        )


def test_mask_is_rejected_when_nothing_is_stored() -> None:
    api = ApiDefinition(name="Yeni", url="https://x.com")

    with pytest.raises(InvalidInput, match="'token'"):
        api.change_auth(AuthType.BEARER, {"token": MASK}, encrypt=encrypt, decrypt=decrypt)


def test_auth_none_clears_the_stored_secret() -> None:
    api = bearer_api()

    api.change_auth(AuthType.NONE, {}, encrypt=encrypt, decrypt=decrypt)

    assert api.auth_config_encrypted is None
    assert api.stored_auth(decrypt) == {}


def test_unreadable_auth_gives_a_clear_message() -> None:
    api = ApiDefinition(name="Bozuk", url="https://x.com", auth_config_encrypted="xx")

    with pytest.raises(SecretUnreadable, match="Kimlik bilgisi çözülemedi"):
        api.stored_auth(decrypt)


def test_json_body_must_be_valid() -> None:
    check_json_body(BodyType.JSON, '{"a": 1}')
    check_json_body(BodyType.TEXT, "{bozuk")
    check_json_body(BodyType.JSON, "   ")
    with pytest.raises(InvalidInput, match="geçerli bir JSON değil"):
        check_json_body(BodyType.JSON, "{bozuk")


def test_apply_changes_checks_new_body_type_against_old_body() -> None:
    api = ApiDefinition(name="X", url="https://x.com", body_type=BodyType.TEXT, body="düz metin")

    with pytest.raises(InvalidInput):
        api.apply_changes({"body_type": BodyType.JSON})
    assert api.body_type == BodyType.TEXT


def test_apply_changes_ignores_none_except_for_clearable_fields() -> None:
    api = ApiDefinition(name="X", url="https://x.com", description="açıklama", body="b")

    api.apply_changes({"name": None, "url": "https://y.com", "description": None, "body": None})

    assert (api.name, api.url, api.description, api.body) == ("X", "https://y.com", None, None)


@pytest.mark.parametrize(
    "method", [HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH, HttpMethod.DELETE]
)
def test_production_needs_confirmation_for_mutating_methods(method) -> None:
    prod = Environment(name="Prod", is_production=True)

    with pytest.raises(ProductionConfirmationRequired, match="'Prod' bir Production ortamı"):
        ensure_production_confirmed(prod, method, confirmed=False)
    ensure_production_confirmed(prod, method, confirmed=True)


def test_read_requests_and_non_production_need_no_confirmation() -> None:
    ensure_production_confirmed(Environment(name="Prod", is_production=True), HttpMethod.GET, False)
    ensure_production_confirmed(Environment(name="Stage"), HttpMethod.DELETE, False)
