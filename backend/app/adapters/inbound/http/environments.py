"""Giren adaptör: ortam yönetimi.

Yetkiler:
- Herkes (giriş yapmış): ortamları ve değişkenleri görebilir (gizli değerler maskeli)
- Admin ve Tester: ortam ekler, değiştirir, siler
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.adapters.inbound.http.dependencies import (
    CipherDep,
    CurrentUser,
    Environments,
    require_roles,
)
from app.adapters.inbound.http.schemas.environment import (
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentUpdate,
    VariableIn,
    VariableRead,
)
from app.application.use_cases.environments import (
    UNCHANGED,
    CreateEnvironment,
    DeleteEnvironment,
    GetEnvironment,
    ListEnvironments,
    UpdateEnvironment,
)
from app.domain.environments import Environment, VariableInput
from app.domain.users import Role, User

router = APIRouter(
    prefix="/environments",
    tags=["Ortamlar"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Editor = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
NOT_FOUND = {404: {"description": "Ortam bulunamadı"}}
FORBIDDEN = {403: {"description": "Sadece Admin ve Tester"}}


def get_list_environments(environments: Environments) -> ListEnvironments:
    return ListEnvironments(environments)


def get_get_environment(environments: Environments) -> GetEnvironment:
    return GetEnvironment(environments)


def get_create_environment(environments: Environments, cipher: CipherDep) -> CreateEnvironment:
    return CreateEnvironment(environments, cipher)


def get_update_environment(environments: Environments, cipher: CipherDep) -> UpdateEnvironment:
    return UpdateEnvironment(environments, cipher)


def get_delete_environment(environments: Environments) -> DeleteEnvironment:
    return DeleteEnvironment(environments)


def _to_input(items: list[VariableIn]) -> list[VariableInput]:
    return [VariableInput(key=i.key, value=i.value, is_secret=i.is_secret) for i in items]


def _to_read(environment: Environment) -> EnvironmentRead:
    return EnvironmentRead(
        id=environment.id,
        name=environment.name,
        description=environment.description,
        is_production=environment.is_production,
        variables=[
            VariableRead(
                key=variable.key,
                value=variable.display_value,
                is_secret=variable.is_secret,
            )
            for variable in environment.variables
        ],
        created_at=environment.created_at,
        updated_at=environment.updated_at,
    )


@router.get("", response_model=list[EnvironmentRead], summary="Ortamları listele")
def list_environments(
    _: CurrentUser,
    use_case: Annotated[ListEnvironments, Depends(get_list_environments)],
) -> list[EnvironmentRead]:
    return [_to_read(environment) for environment in use_case()]


@router.post(
    "",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni ortam",
    responses={**FORBIDDEN, 409: {"description": "Bu adda ortam var"}},
)
def create_environment(
    body: EnvironmentCreate,
    _: Editor,
    use_case: Annotated[CreateEnvironment, Depends(get_create_environment)],
) -> EnvironmentRead:
    environment = use_case(
        name=body.name,
        description=body.description,
        is_production=body.is_production,
        variables=_to_input(body.variables),
    )
    return _to_read(environment)


@router.get(
    "/{environment_id}",
    response_model=EnvironmentRead,
    summary="Ortam detayı",
    responses=NOT_FOUND,
)
def get_environment(
    environment_id: int,
    _: CurrentUser,
    use_case: Annotated[GetEnvironment, Depends(get_get_environment)],
) -> EnvironmentRead:
    return _to_read(use_case(environment_id))


@router.patch(
    "/{environment_id}",
    response_model=EnvironmentRead,
    summary="Ortamı güncelle",
    responses={**NOT_FOUND, **FORBIDDEN, 409: {"description": "Bu adda ortam var"}},
)
def update_environment(
    environment_id: int,
    body: EnvironmentUpdate,
    _: Editor,
    use_case: Annotated[UpdateEnvironment, Depends(get_update_environment)],
) -> EnvironmentRead:
    environment = use_case(
        environment_id,
        name=body.name,
        # description gönderilmediyse dokunma; null gönderildiyse boşalt
        description=body.description if "description" in body.model_fields_set else UNCHANGED,
        is_production=body.is_production,
        variables=_to_input(body.variables) if body.variables is not None else None,
    )
    return _to_read(environment)


@router.delete(
    "/{environment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ortamı sil",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_environment(
    environment_id: int,
    _: Editor,
    use_case: Annotated[DeleteEnvironment, Depends(get_delete_environment)],
) -> None:
    use_case(environment_id)
