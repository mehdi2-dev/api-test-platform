"""Use case'ler: API tanımı yönetimi ve göndermeye hazırlık."""

from dataclasses import dataclass, field
from typing import Any

from app.application.ports.api_definitions import ApiDefinitionRepository
from app.application.ports.environments import EnvironmentRepository
from app.application.ports.security import Cipher
from app.application.use_cases.environments import GetEnvironment
from app.domain.api_definitions import (
    ApiDefinition,
    AuthType,
    BodyType,
    HttpMethod,
    ensure_production_confirmed,
)
from app.domain.errors import NotFound
from app.domain.users import User


class ListApiDefinitions:
    def __init__(self, apis: ApiDefinitionRepository) -> None:
        self._apis = apis

    def __call__(self, name_contains: str | None = None) -> list[ApiDefinition]:
        return self._apis.search(name_contains)


class GetApiDefinition:
    def __init__(self, apis: ApiDefinitionRepository) -> None:
        self._apis = apis

    def __call__(self, api_id: int) -> ApiDefinition:
        api = self._apis.get(api_id)
        if api is None:
            raise NotFound("API tanımı bulunamadı")
        return api


class CreateApiDefinition:
    def __init__(self, apis: ApiDefinitionRepository, cipher: Cipher) -> None:
        self._apis = apis
        self._cipher = cipher

    def __call__(
        self,
        *,
        created_by: User,
        name: str,
        description: str | None,
        method: HttpMethod,
        url: str,
        headers: list[dict[str, Any]],
        query_params: list[dict[str, Any]],
        body_type: BodyType,
        body: str | None,
        assertions: list[dict[str, Any]],
        auth_type: AuthType,
        auth_fields: dict[str, Any],
    ) -> ApiDefinition:
        api = ApiDefinition(
            name=name,
            description=description,
            method=method,
            url=url,
            headers=headers,
            query_params=query_params,
            body_type=body_type,
            body=body,
            assertions=assertions,
            auth_type=AuthType.NONE,
            created_by_id=created_by.id,
        )
        api.change_auth(
            auth_type, auth_fields, encrypt=self._cipher.encrypt, decrypt=self._cipher.decrypt
        )
        self._apis.save(api)
        return api


class UpdateApiDefinition:
    def __init__(self, apis: ApiDefinitionRepository, cipher: Cipher) -> None:
        self._apis = apis
        self._cipher = cipher

    def __call__(
        self,
        api_id: int,
        *,
        changes: dict[str, Any],
        assertions: list[dict[str, Any]] | None = None,
        auth_type: AuthType | None = None,
        auth_fields: dict[str, Any] | None = None,
    ) -> ApiDefinition:
        api = GetApiDefinition(self._apis)(api_id)
        api.apply_changes(changes)
        if assertions is not None:
            api.assertions = assertions
        if auth_type is not None:
            api.change_auth(
                auth_type,
                auth_fields or {},
                encrypt=self._cipher.encrypt,
                decrypt=self._cipher.decrypt,
            )
        self._apis.save(api)
        return api


class DeleteApiDefinition:
    def __init__(self, apis: ApiDefinitionRepository) -> None:
        self._apis = apis

    def __call__(self, api_id: int) -> None:
        self._apis.delete(GetApiDefinition(self._apis)(api_id))


@dataclass
class PreparedRequest:
    """Göndermeye hazır istek: tanım, çözülmüş kimlik bilgisi ve ortam değişkenleri."""

    api: ApiDefinition
    auth: dict[str, Any]
    variables: dict[str, str] = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    environment_name: str | None = None


class PrepareApiRequest:
    """Tanımı ve (varsa) ortamı yükler, Production kuralını uygular."""

    def __init__(
        self,
        apis: ApiDefinitionRepository,
        environments: EnvironmentRepository,
        cipher: Cipher,
    ) -> None:
        self._apis = apis
        self._environments = environments
        self._cipher = cipher

    def __call__(
        self,
        api_id: int,
        *,
        environment_id: int | None = None,
        confirm_production: bool = False,
    ) -> PreparedRequest:
        api = GetApiDefinition(self._apis)(api_id)
        prepared = PreparedRequest(api=api, auth={})

        if environment_id is not None:
            environment = GetEnvironment(self._environments)(environment_id)
            prepared.environment_name = environment.name
            prepared.variables, prepared.secrets = environment.resolve_variables(
                self._cipher.decrypt
            )
            ensure_production_confirmed(environment, api.method, confirm_production)

        prepared.auth = api.stored_auth(self._cipher.decrypt)
        return prepared
