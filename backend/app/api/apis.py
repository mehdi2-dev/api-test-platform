"""API tanımları: listeleme, oluşturma, güncelleme, silme ve tekil gönderme.

Yetkiler:
- Herkes (giriş yapmış): listeleyebilir ve görüntüleyebilir (gizli değerler maskeli)
- Admin ve Tester: oluşturabilir, değiştirebilir, silebilir, gönderebilir
"""

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require_roles
from app.core.crypto import decrypt_json, encrypt_json
from app.models.api_definition import ApiDefinition, AuthType
from app.models.user import Role, User
from app.schemas.api_definition import (
    MASK,
    SECRET_FIELDS,
    ApiDefinitionCreate,
    ApiDefinitionRead,
    ApiDefinitionUpdate,
    AuthConfig,
    SendResult,
    check_json_body,
    masked_auth,
)
from app.services import http_runner

router = APIRouter(
    prefix="/apis",
    tags=["API Yönetimi"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Editor = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
NOT_FOUND = {404: {"description": "API tanımı bulunamadı"}}
FORBIDDEN = {403: {"description": "Sadece Admin ve Tester"}}


def get_http_transport() -> httpx.BaseTransport | None:
    """Testlerde sahte bir transport ile değiştirilir; normalde gerçek ağ kullanılır."""
    return None


HttpTransport = Annotated[httpx.BaseTransport | None, Depends(get_http_transport)]


def _get_or_404(db: DbSession, api_id: int) -> ApiDefinition:
    api = db.get(ApiDefinition, api_id)
    if api is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="API tanımı bulunamadı")
    return api


def _stored_auth(api: ApiDefinition) -> dict[str, Any]:
    try:
        return decrypt_json(api.auth_config_encrypted)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kimlik bilgisi çözülemedi; şifreleme anahtarı değişmiş olabilir",
        ) from exc


def _to_read(api: ApiDefinition) -> ApiDefinitionRead:
    return ApiDefinitionRead(
        id=api.id,
        name=api.name,
        description=api.description,
        method=api.method,
        url=api.url,
        headers=api.headers or [],
        query_params=api.query_params or [],
        body_type=api.body_type,
        body=api.body,
        auth=masked_auth(api.auth_type, _stored_auth(api)),
        created_by_id=api.created_by_id,
        created_at=api.created_at,
        updated_at=api.updated_at,
    )


def _apply_auth(api: ApiDefinition, auth: AuthConfig, previous: dict[str, Any]) -> None:
    """Auth ayarını şifreleyip kaydeder. MASK gelen gizli alanlarda eski değer korunur."""
    fields = auth.stored_fields()
    for name in SECRET_FIELDS:
        if fields.get(name) == MASK:
            if not previous.get(name) or auth.type != api.auth_type:
                raise HTTPException(
                    422,
                    detail=f"'{name}' için kayıtlı değer yok, lütfen yeni değer girin",
                )
            fields[name] = previous[name]

    api.auth_type = auth.type
    api.auth_config_encrypted = encrypt_json(fields) if auth.type != AuthType.NONE else None


@router.get("", response_model=list[ApiDefinitionRead], summary="API tanımlarını listele")
def list_apis(
    _: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(description="Ada göre arama")] = None,
) -> list[ApiDefinitionRead]:
    query = select(ApiDefinition).order_by(ApiDefinition.name, ApiDefinition.id)
    if q:
        query = query.where(ApiDefinition.name.ilike(f"%{q}%"))
    return [_to_read(api) for api in db.scalars(query)]


@router.post(
    "",
    response_model=ApiDefinitionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni API tanımı",
    responses=FORBIDDEN,
)
def create_api(body: ApiDefinitionCreate, user: Editor, db: DbSession) -> ApiDefinitionRead:
    api = ApiDefinition(
        name=body.name,
        description=body.description,
        method=body.method,
        url=body.url,
        headers=[item.model_dump() for item in body.headers],
        query_params=[item.model_dump() for item in body.query_params],
        body_type=body.body_type,
        body=body.body,
        auth_type=AuthType.NONE,
        created_by_id=user.id,
    )
    _apply_auth(api, body.auth, previous={})
    db.add(api)
    db.commit()
    db.refresh(api)
    return _to_read(api)


@router.get(
    "/{api_id}",
    response_model=ApiDefinitionRead,
    summary="API tanımı detayı",
    responses=NOT_FOUND,
)
def get_api(api_id: int, _: CurrentUser, db: DbSession) -> ApiDefinitionRead:
    return _to_read(_get_or_404(db, api_id))


@router.patch(
    "/{api_id}",
    response_model=ApiDefinitionRead,
    summary="API tanımını güncelle",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def update_api(
    api_id: int, body: ApiDefinitionUpdate, _: Editor, db: DbSession
) -> ApiDefinitionRead:
    api = _get_or_404(db, api_id)
    changes = body.model_dump(exclude_unset=True, exclude={"auth"})

    # Body tipi ve içeriği birlikte geçerli olmalı (biri eski, biri yeni olabilir)
    try:
        check_json_body(changes.get("body_type", api.body_type), changes.get("body", api.body))
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc

    for field in ("name", "method", "url", "body_type"):
        if changes.get(field) is not None:
            setattr(api, field, changes[field])
    for field in ("description", "body"):
        if field in changes:
            setattr(api, field, changes[field])
    for field in ("headers", "query_params"):
        if changes.get(field) is not None:
            setattr(api, field, changes[field])

    if body.auth is not None:
        _apply_auth(api, body.auth, previous=_stored_auth(api))

    db.commit()
    db.refresh(api)
    return _to_read(api)


@router.delete(
    "/{api_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="API tanımını sil",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_api(api_id: int, _: Editor, db: DbSession) -> None:
    db.delete(_get_or_404(db, api_id))
    db.commit()


@router.post(
    "/{api_id}/send",
    response_model=SendResult,
    summary="İsteği şimdi gönder ve cevabı göster",
    description=(
        "Kayıtlı tanımı olduğu gibi gönderir. Hedef sunucu hata kodu dönse bile bu endpoint "
        "200 döner; sonucun kendisi status_code alanındadır. Bağlantı kurulamazsa ok=false "
        "ve error alanı dolu gelir."
    ),
    responses={**NOT_FOUND, **FORBIDDEN},
)
def send_api(api_id: int, _: Editor, db: DbSession, transport: HttpTransport) -> SendResult:
    api = _get_or_404(db, api_id)
    return http_runner.send(api, _stored_auth(api), transport=transport)
