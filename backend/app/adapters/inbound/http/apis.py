"""Giren adaptör: API tanımları; listeleme, oluşturma, güncelleme, silme ve tekil gönderme.

Yetkiler:
- Herkes (giriş yapmış): listeleyebilir ve görüntüleyebilir (gizli değerler maskeli)
- Admin ve Tester: oluşturabilir, değiştirebilir, silebilir, gönderebilir

Not: İsteği gerçekten gönderen http_runner ve test sonucunu kaydeden servisler ATOP-63'te
portlara taşınacak; şimdilik bu adaptör onları doğrudan çağırıyor.
"""

import json
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query, status

from app.adapters.inbound.http.dependencies import (
    ApiDefinitions,
    CipherDep,
    CurrentUser,
    DbSession,
    Environments,
    require_roles,
)
from app.application.ports.security import Cipher
from app.application.use_cases.api_definitions import (
    CreateApiDefinition,
    DeleteApiDefinition,
    GetApiDefinition,
    ListApiDefinitions,
    PrepareApiRequest,
    PreparedRequest,
    UpdateApiDefinition,
)
from app.domain.api_definitions import ApiDefinition
from app.domain.errors import ProductionConfirmationRequired
from app.domain.users import Role, User
from app.schemas.api_definition import (
    ApiDefinitionCreate,
    ApiDefinitionRead,
    ApiDefinitionUpdate,
    SendResult,
    masked_auth,
)
from app.schemas.assertion import TestRunRead
from app.schemas.environment import SendOptions
from app.services import http_runner
from app.services.assertions import evaluate
from app.services.masking import mask_headers, mask_text
from app.services.test_runs import run_to_read, save_run

router = APIRouter(
    prefix="/apis",
    tags=["API Yönetimi"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Editor = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
NOT_FOUND = {404: {"description": "API tanımı veya ortam bulunamadı"}}
PRODUCTION_CONFIRMATION = ProductionConfirmationRequired.code
FORBIDDEN = {403: {"description": "Sadece Admin ve Tester"}}


def get_http_transport() -> httpx.BaseTransport | None:
    """Testlerde sahte bir transport ile değiştirilir; normalde gerçek ağ kullanılır."""
    return None


HttpTransport = Annotated[httpx.BaseTransport | None, Depends(get_http_transport)]


def get_list_apis(apis: ApiDefinitions) -> ListApiDefinitions:
    return ListApiDefinitions(apis)


def get_get_api(apis: ApiDefinitions) -> GetApiDefinition:
    return GetApiDefinition(apis)


def get_create_api(apis: ApiDefinitions, cipher: CipherDep) -> CreateApiDefinition:
    return CreateApiDefinition(apis, cipher)


def get_update_api(apis: ApiDefinitions, cipher: CipherDep) -> UpdateApiDefinition:
    return UpdateApiDefinition(apis, cipher)


def get_delete_api(apis: ApiDefinitions) -> DeleteApiDefinition:
    return DeleteApiDefinition(apis)


def get_prepare_request(
    apis: ApiDefinitions, environments: Environments, cipher: CipherDep
) -> PrepareApiRequest:
    return PrepareApiRequest(apis, environments, cipher)


def _to_read(api: ApiDefinition, cipher: Cipher) -> ApiDefinitionRead:
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
        auth=masked_auth(api.auth_type, api.stored_auth(cipher.decrypt)),
        assertions=api.assertions or [],
        created_by_id=api.created_by_id,
        created_at=api.created_at,
        updated_at=api.updated_at,
    )


@router.get("", response_model=list[ApiDefinitionRead], summary="API tanımlarını listele")
def list_apis(
    _: CurrentUser,
    cipher: CipherDep,
    use_case: Annotated[ListApiDefinitions, Depends(get_list_apis)],
    q: Annotated[str | None, Query(description="Ada göre arama")] = None,
) -> list[ApiDefinitionRead]:
    return [_to_read(api, cipher) for api in use_case(q)]


@router.post(
    "",
    response_model=ApiDefinitionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni API tanımı",
    responses=FORBIDDEN,
)
def create_api(
    body: ApiDefinitionCreate,
    user: Editor,
    cipher: CipherDep,
    use_case: Annotated[CreateApiDefinition, Depends(get_create_api)],
) -> ApiDefinitionRead:
    api = use_case(
        created_by=user,
        name=body.name,
        description=body.description,
        method=body.method,
        url=body.url,
        headers=[item.model_dump() for item in body.headers],
        query_params=[item.model_dump() for item in body.query_params],
        body_type=body.body_type,
        body=body.body,
        assertions=[item.model_dump(mode="json") for item in body.assertions],
        auth_type=body.auth.type,
        auth_fields=body.auth.stored_fields(),
    )
    return _to_read(api, cipher)


@router.get(
    "/{api_id}",
    response_model=ApiDefinitionRead,
    summary="API tanımı detayı",
    responses=NOT_FOUND,
)
def get_api(
    api_id: int,
    _: CurrentUser,
    cipher: CipherDep,
    use_case: Annotated[GetApiDefinition, Depends(get_get_api)],
) -> ApiDefinitionRead:
    return _to_read(use_case(api_id), cipher)


@router.patch(
    "/{api_id}",
    response_model=ApiDefinitionRead,
    summary="API tanımını güncelle",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def update_api(
    api_id: int,
    body: ApiDefinitionUpdate,
    _: Editor,
    cipher: CipherDep,
    use_case: Annotated[UpdateApiDefinition, Depends(get_update_api)],
) -> ApiDefinitionRead:
    api = use_case(
        api_id,
        changes=body.model_dump(exclude_unset=True, exclude={"auth", "assertions"}),
        assertions=(
            [item.model_dump(mode="json") for item in body.assertions]
            if body.assertions is not None
            else None
        ),
        auth_type=body.auth.type if body.auth is not None else None,
        auth_fields=body.auth.stored_fields() if body.auth is not None else None,
    )
    return _to_read(api, cipher)


@router.delete(
    "/{api_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="API tanımını sil",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_api(
    api_id: int,
    _: Editor,
    use_case: Annotated[DeleteApiDefinition, Depends(get_delete_api)],
) -> None:
    use_case(api_id)


def _prepare(use_case: PrepareApiRequest, api_id: int, options: SendOptions) -> PreparedRequest:
    return use_case(
        api_id,
        environment_id=options.environment_id,
        confirm_production=options.confirm_production,
    )


def _send(prepared: PreparedRequest, transport: httpx.BaseTransport | None) -> SendResult:
    return http_runner.send(
        prepared.api,
        prepared.auth,
        transport=transport,
        variables=prepared.variables,
        secret_values=prepared.secrets,
        environment_name=prepared.environment_name,
    )


@router.post(
    "/{api_id}/send",
    response_model=SendResult,
    summary="İsteği şimdi gönder ve cevabı göster",
    description=(
        "Kayıtlı tanımı gönderir. environment_id verilirse {{değişken}}'ler o ortamın "
        "değerleriyle doldurulur. Hedef sunucu hata kodu dönse bile bu endpoint 200 döner; "
        "sonucun kendisi status_code alanındadır. Bağlantı kurulamazsa ok=false ve error "
        "alanı dolu gelir.\n\n"
        "Production ortamında POST/PUT/PATCH/DELETE istekleri confirm_production=true "
        "olmadan çalışmaz (409)."
    ),
    responses={
        **NOT_FOUND,
        **FORBIDDEN,
        409: {
            "description": "Production ortamında veri değiştiren istek için onay gerekli",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": PRODUCTION_CONFIRMATION,
                            "message": "Prod ortamında POST isteği veri değiştirebilir.",
                        }
                    }
                }
            },
        },
    },
)
def send_api(
    api_id: int,
    _: Editor,
    transport: HttpTransport,
    use_case: Annotated[PrepareApiRequest, Depends(get_prepare_request)],
    options: SendOptions | None = None,
) -> SendResult:
    prepared = _prepare(use_case, api_id, options or SendOptions())
    result = _send(prepared, transport)
    # Ekrana dönen cevapta da gizli değerler ve hassas alanlar maskelenir
    masked_body = mask_text(result.body, prepared.secrets)
    if masked_body != result.body:
        result.body = masked_body
        result.body_json = json.loads(masked_body) if result.body_json is not None else None
    result.headers = mask_headers(result.headers, prepared.secrets)
    return result


@router.post(
    "/{api_id}/run",
    response_model=TestRunRead,
    summary="Testi çalıştır: gönder, kuralları uygula, sonucu kaydet",
    description=(
        "send ile aynı isteği gönderir; ardından API'nin kurallarını (assertions) cevaba "
        "uygular ve sonucu test geçmişine kaydeder. status: passed (tüm kurallar geçti), "
        "failed (en az bir kural kaldı) veya error (cevap alınamadı)."
    ),
    responses={**NOT_FOUND, **FORBIDDEN, 409: {"description": "Production onayı gerekli"}},
)
def run_api(
    api_id: int,
    user: Editor,
    db: DbSession,
    transport: HttpTransport,
    use_case: Annotated[PrepareApiRequest, Depends(get_prepare_request)],
    options: SendOptions | None = None,
) -> TestRunRead:
    prepared = _prepare(use_case, api_id, options or SendOptions())
    result = _send(prepared, transport)
    results = evaluate(prepared.api.assertions or [], result, prepared.variables)
    run = save_run(db, prepared.api, result, results, user.id, secret_values=prepared.secrets)
    return run_to_read(run)
