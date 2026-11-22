"""Ortam yönetimi (ATOP-27, ATOP-29).

Yetkiler:
- Herkes (giriş yapmış): ortamları ve değişkenleri görebilir (gizli değerler maskeli)
- Admin ve Tester: ortam ekler, değiştirir, siler
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core.crypto import decrypt_text, encrypt_text
from app.models.environment import Environment, EnvironmentVariable
from app.models.user import Role, User
from app.schemas.api_definition import MASK
from app.schemas.environment import (
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentUpdate,
    VariableIn,
    VariableRead,
)

router = APIRouter(
    prefix="/environments",
    tags=["Ortamlar"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Editor = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
NOT_FOUND = {404: {"description": "Ortam bulunamadı"}}
FORBIDDEN = {403: {"description": "Sadece Admin ve Tester"}}


def get_environment_or_404(db: DbSession, environment_id: int) -> Environment:
    environment = db.get(Environment, environment_id)
    if environment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ortam bulunamadı")
    return environment


def variable_values(environment: Environment) -> tuple[dict[str, str], list[str]]:
    """Ortamın değişkenlerini çözülmüş halde döndürür: (ad -> değer, gizli değerler)."""
    values: dict[str, str] = {}
    secrets: list[str] = []
    for variable in environment.variables:
        if variable.is_secret and variable.value:
            try:
                plain = decrypt_text(variable.value)
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"'{variable.key}' çözülemedi; şifreleme anahtarı değişmiş olabilir",
                ) from exc
            secrets.append(plain)
        else:
            plain = variable.value
        values[variable.key] = plain
    return values, secrets


def _to_read(environment: Environment) -> EnvironmentRead:
    return EnvironmentRead(
        id=environment.id,
        name=environment.name,
        description=environment.description,
        is_production=environment.is_production,
        variables=[
            VariableRead(
                key=variable.key,
                value=MASK if variable.is_secret and variable.value else variable.value,
                is_secret=variable.is_secret,
            )
            for variable in environment.variables
        ],
        created_at=environment.created_at,
        updated_at=environment.updated_at,
    )


def _check_name_free(db: DbSession, name: str, own_id: int | None = None) -> None:
    other = db.scalar(select(Environment).where(Environment.name == name))
    if other is not None and other.id != own_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"'{name}' adında bir ortam zaten var")


def _apply_variables(environment: Environment, incoming: list[VariableIn]) -> None:
    """Değişken listesini gelenle değiştirir.

    Aynı adlı mevcut satırlar güncellenir (silip yeniden eklemek benzersizlik kuralına
    takılabilir). Gizli bir değişken için MASK gelirse kayıtlı değer korunur.
    """
    existing = {variable.key: variable for variable in environment.variables}
    result: list[EnvironmentVariable] = []

    for item in incoming:
        previous = existing.pop(item.key, None)
        if item.is_secret and item.value == MASK:
            if previous is None or not previous.is_secret:
                raise HTTPException(
                    422, detail=f"'{item.key}' için kayıtlı gizli değer yok, yeni değer girin"
                )
            stored = previous.value
        elif item.is_secret and item.value:
            stored = encrypt_text(item.value)
        else:
            stored = item.value

        variable = previous or EnvironmentVariable(key=item.key)
        variable.value = stored
        variable.is_secret = item.is_secret
        result.append(variable)

    # Listede olmayanlar (existing'de kalanlar) delete-orphan ile silinir
    environment.variables = result


@router.get("", response_model=list[EnvironmentRead], summary="Ortamları listele")
def list_environments(_: CurrentUser, db: DbSession) -> list[EnvironmentRead]:
    query = select(Environment).order_by(Environment.is_production, Environment.name)
    return [_to_read(environment) for environment in db.scalars(query)]


@router.post(
    "",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni ortam",
    responses={**FORBIDDEN, 409: {"description": "Bu adda ortam var"}},
)
def create_environment(body: EnvironmentCreate, _: Editor, db: DbSession) -> EnvironmentRead:
    _check_name_free(db, body.name)
    environment = Environment(
        name=body.name, description=body.description, is_production=body.is_production
    )
    _apply_variables(environment, body.variables)
    db.add(environment)
    db.commit()
    db.refresh(environment)
    return _to_read(environment)


@router.get(
    "/{environment_id}",
    response_model=EnvironmentRead,
    summary="Ortam detayı",
    responses=NOT_FOUND,
)
def get_environment(environment_id: int, _: CurrentUser, db: DbSession) -> EnvironmentRead:
    return _to_read(get_environment_or_404(db, environment_id))


@router.patch(
    "/{environment_id}",
    response_model=EnvironmentRead,
    summary="Ortamı güncelle",
    responses={**NOT_FOUND, **FORBIDDEN, 409: {"description": "Bu adda ortam var"}},
)
def update_environment(
    environment_id: int, body: EnvironmentUpdate, _: Editor, db: DbSession
) -> EnvironmentRead:
    environment = get_environment_or_404(db, environment_id)

    if body.name is not None:
        _check_name_free(db, body.name, own_id=environment.id)
        environment.name = body.name
    if "description" in body.model_fields_set:
        environment.description = body.description
    if body.is_production is not None:
        environment.is_production = body.is_production
    if body.variables is not None:
        _apply_variables(environment, body.variables)

    db.commit()
    db.refresh(environment)
    return _to_read(environment)


@router.delete(
    "/{environment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Ortamı sil",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_environment(environment_id: int, _: Editor, db: DbSession) -> None:
    db.delete(get_environment_or_404(db, environment_id))
    db.commit()
