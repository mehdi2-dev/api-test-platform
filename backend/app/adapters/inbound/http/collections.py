"""Giren adaptör: koleksiyonlar; oluşturma, sıralama, çalıştırma, içe/dışa aktarma.

Yetkiler:
- Herkes (giriş yapmış): koleksiyonları, çalıştırma sonuçlarını görür, dışa aktarır
- Admin ve Tester: oluşturur, değiştirir, siler, çalıştırır, içe aktarır
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import ValidationError

from app.adapters.inbound.http.apis import PRODUCTION_CONFIRMATION, HttpTransport
from app.adapters.inbound.http.dependencies import (
    ApiDefinitions,
    CipherDep,
    CollectionRuns,
    Collections,
    CurrentUser,
    DbSession,
    Environments,
    TestRuns,
    require_roles,
)
from app.adapters.inbound.http.presenters import run_to_read
from app.adapters.inbound.http.schemas.api_definition import ApiDefinitionCreate
from app.adapters.inbound.http.schemas.collection import (
    CollectionCreate,
    CollectionExport,
    CollectionItemIn,
    CollectionItemRead,
    CollectionRead,
    CollectionRunRead,
    CollectionRunSummary,
    CollectionSummary,
    CollectionUpdate,
    DemoSeedResult,
    ImportResult,
    StepResult,
)
from app.adapters.inbound.http.schemas.environment import SendOptions
from app.adapters.outbound.queue import CallableRunQueue
from app.application.use_cases.collections import (
    CollectionRunDetails,
    CreateCollection,
    DeleteCollection,
    ExportCollection,
    GetCollection,
    GetCollectionRun,
    ImportCollection,
    ImportedApi,
    ImportedStep,
    ListCollectionRuns,
    ListCollections,
    QueueCollectionRun,
    StartCollectionRun,
    UpdateCollection,
)
from app.application.use_cases.environments import UNCHANGED
from app.composition import Enqueue, celery_enqueue, preparer, runner
from app.domain.api_definitions import SECRET_AUTH_FIELDS
from app.domain.collections import Collection, CollectionItem, CollectionRun, StepInput
from app.domain.errors import InvalidInput
from app.domain.secrets import MASK
from app.domain.users import Role, User

router = APIRouter(
    prefix="/collections",
    tags=["Koleksiyonlar"],
    responses={401: {"description": "Giriş yapılmamış"}},
)

Editor = Annotated[User, Depends(require_roles(Role.ADMIN, Role.TESTER))]
AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
NOT_FOUND = {404: {"description": "Koleksiyon bulunamadı"}}
FORBIDDEN = {403: {"description": "Sadece Admin ve Tester"}}
CONFLICT = {409: {"description": "Bu adda koleksiyon var"}}


def get_enqueuer() -> Enqueue:
    """Testlerde Celery olmadan çalışan bir sürümle değiştirilir."""
    return celery_enqueue


Enqueuer = Annotated[Enqueue, Depends(get_enqueuer)]


# --- Use case'lerin kurulumu ---


def get_list(collections: Collections, runs: CollectionRuns) -> ListCollections:
    return ListCollections(collections, runs)


def get_get(collections: Collections) -> GetCollection:
    return GetCollection(collections)


def get_create(collections: Collections, apis: ApiDefinitions) -> CreateCollection:
    return CreateCollection(collections, apis)


def get_update(collections: Collections, apis: ApiDefinitions) -> UpdateCollection:
    return UpdateCollection(collections, apis)


def get_delete(collections: Collections) -> DeleteCollection:
    return DeleteCollection(collections)


def get_export(collections: Collections, cipher: CipherDep) -> ExportCollection:
    return ExportCollection(collections, cipher)


def get_import(
    collections: Collections, apis: ApiDefinitions, cipher: CipherDep
) -> ImportCollection:
    return ImportCollection(collections, apis, cipher)


def get_start_run(
    db: DbSession,
    collections: Collections,
    environments: Environments,
    test_runs: TestRuns,
    transport: HttpTransport,
) -> StartCollectionRun:
    return StartCollectionRun(
        collections, environments, preparer(db), runner(db, transport), test_runs
    )


def get_queue_run(
    db: DbSession,
    collections: Collections,
    environments: Environments,
    runs: CollectionRuns,
    enqueue: Enqueuer,
) -> QueueCollectionRun:
    return QueueCollectionRun(
        collections, environments, preparer(db), runs, CallableRunQueue(enqueue)
    )


def get_list_runs(collections: Collections, runs: CollectionRuns) -> ListCollectionRuns:
    return ListCollectionRuns(collections, runs)


def get_get_run(runs: CollectionRuns, test_runs: TestRuns) -> GetCollectionRun:
    return GetCollectionRun(runs, test_runs)


# --- HTTP şemalarına çevirme ---


def _steps(items: list[CollectionItemIn]) -> list[StepInput]:
    return [
        StepInput(
            api_definition_id=item.api_definition_id,
            enabled=item.enabled,
            extractions=[extraction.model_dump() for extraction in item.extractions],
        )
        for item in items
    ]


def _item_read(item: CollectionItem) -> CollectionItemRead:
    api = item.api
    return CollectionItemRead(
        id=item.id,
        position=item.position,
        api_definition_id=item.api_definition_id,
        api_name=api.name if api else "(silinmiş API)",
        method=api.method.value if api else "-",
        url=api.url if api else "",
        enabled=item.enabled,
        extractions=item.extractions or [],
    )


def _to_read(collection: Collection) -> CollectionRead:
    return CollectionRead(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        stop_on_failure=collection.stop_on_failure,
        items=[_item_read(item) for item in collection.items],
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def run_summary_fields(run: CollectionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "collection_id": run.collection_id,
        "collection_name": run.collection_name,
        "environment_name": run.environment_name,
        "state": run.state,
        "trigger": run.trigger,
        "schedule_id": run.schedule_id,
        "status": run.status,
        "error": run.error,
        "total_steps": run.total_steps,
        "passed_steps": run.passed_steps,
        "failed_steps": run.failed_steps,
        "skipped_steps": run.skipped_steps,
        "elapsed_ms": run.elapsed_ms,
        "triggered_by_id": run.triggered_by_id,
        "created_at": run.created_at,
    }


def _run_read(details: CollectionRunDetails) -> CollectionRunRead:
    return CollectionRunRead(
        **run_summary_fields(details.run),
        steps=[StepResult.model_validate(step) for step in details.run.steps or []],
        step_runs={test_run.id: run_to_read(test_run) for test_run in details.step_runs},
    )


def imported_apis(body: CollectionExport) -> list[ImportedApi]:
    """Dosyadaki API'leri sırayla doğrular; ilk hatalı olanı 422 ile bildirir.

    Maskeli (********) gizli değer içe aktarılamaz: gerçek değeri bilinmiyor.
    """
    result: list[ImportedApi] = []
    for index, exported in enumerate(body.apis, start=1):
        try:
            definition = ApiDefinitionCreate.model_validate(exported.model_dump())
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first["loc"])
            raise InvalidInput(
                f"{index}. API ({exported.name}) geçersiz: {where}: {first['msg']}"
            ) from exc
        fields = definition.auth.stored_fields()
        if any(fields.get(secret) == MASK for secret in SECRET_AUTH_FIELDS):
            raise InvalidInput(
                f"{index}. API ({exported.name}): maskeli gizli değer içe aktarılamaz"
            )
        result.append(
            ImportedApi(
                name=definition.name,
                description=definition.description,
                method=definition.method,
                url=definition.url,
                headers=[item.model_dump() for item in definition.headers],
                query_params=[item.model_dump() for item in definition.query_params],
                body_type=definition.body_type,
                body=definition.body,
                assertions=[item.model_dump(mode="json") for item in definition.assertions],
                auth_type=definition.auth.type,
                auth_fields=fields,
            )
        )
    return result


def import_from_export(
    use_case: ImportCollection, body: CollectionExport, user_id: int | None
) -> tuple[Collection, int]:
    return use_case(
        name=body.name,
        description=body.description,
        stop_on_failure=body.stop_on_failure,
        apis=imported_apis(body),
        steps=[
            ImportedStep(
                api=step.api,
                enabled=step.enabled,
                extractions=[extraction.model_dump() for extraction in step.extractions],
            )
            for step in body.steps
        ],
        user_id=user_id,
    )


# --- CRUD ---


@router.get("", response_model=list[CollectionSummary], summary="Koleksiyonları listele")
def list_collections(
    _: CurrentUser, use_case: Annotated[ListCollections, Depends(get_list)]
) -> list[CollectionSummary]:
    return [
        CollectionSummary(
            id=row.collection.id,
            name=row.collection.name,
            description=row.collection.description,
            stop_on_failure=row.collection.stop_on_failure,
            item_count=len(row.collection.items),
            last_run_status=row.last_run.status if row.last_run else None,
            last_run_at=row.last_run.created_at if row.last_run else None,
            updated_at=row.collection.updated_at,
        )
        for row in use_case()
    ]


@router.post(
    "",
    response_model=CollectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni koleksiyon",
    responses={**FORBIDDEN, **CONFLICT},
)
def create_collection(
    body: CollectionCreate,
    user: Editor,
    use_case: Annotated[CreateCollection, Depends(get_create)],
) -> CollectionRead:
    collection = use_case(
        created_by=user,
        name=body.name,
        description=body.description,
        stop_on_failure=body.stop_on_failure,
        steps=_steps(body.items),
    )
    return _to_read(collection)


@router.post(
    "/import",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="JSON dosyasından koleksiyon içe aktar",
    description=(
        "Dışa aktarılan JSON'u alır; içindeki API tanımlarını yeni kayıt olarak oluşturur ve "
        "koleksiyonu kurar. Aynı adda koleksiyon varsa adın sonuna (2), (3)... eklenir. "
        "required_variables listesindeki değişkenleri ortama eklemeniz gerekir."
    ),
    responses=FORBIDDEN,
)
def import_collection(
    body: CollectionExport,
    user: Editor,
    use_case: Annotated[ImportCollection, Depends(get_import)],
) -> ImportResult:
    collection, created = import_from_export(use_case, body, user.id)
    return ImportResult(
        collection=_to_read(collection),
        created_apis=created,
        required_variables=body.required_variables,
    )


@router.post(
    "/seed-demo",
    response_model=DemoSeedResult,
    summary="Demo ortamını ve örnek koleksiyonları yükle (Admin)",
    description=(
        "Demo CRM servisi için 'Demo' ortamını (base_url, demo_user, demo_password) ve "
        "backend/examples klasöründeki örnek koleksiyonları oluşturur. Zaten varsa atlar."
    ),
    responses={403: {"description": "Sadece Admin"}},
)
def seed_demo_endpoint(user: AdminUser, db: DbSession) -> DemoSeedResult:
    from app.adapters.inbound.demo_seed import seed_demo

    return seed_demo(db, user.id)


@router.get(
    "/{collection_id}",
    response_model=CollectionRead,
    summary="Koleksiyon detayı",
    responses=NOT_FOUND,
)
def get_collection(
    collection_id: int,
    _: CurrentUser,
    use_case: Annotated[GetCollection, Depends(get_get)],
) -> CollectionRead:
    return _to_read(use_case(collection_id))


@router.patch(
    "/{collection_id}",
    response_model=CollectionRead,
    summary="Koleksiyonu güncelle (adımlar ve sıraları dahil)",
    responses={**NOT_FOUND, **FORBIDDEN, **CONFLICT},
)
def update_collection(
    collection_id: int,
    body: CollectionUpdate,
    _: Editor,
    use_case: Annotated[UpdateCollection, Depends(get_update)],
) -> CollectionRead:
    collection = use_case(
        collection_id,
        name=body.name,
        description=body.description if "description" in body.model_fields_set else UNCHANGED,
        stop_on_failure=body.stop_on_failure,
        steps=_steps(body.items) if body.items is not None else None,
    )
    return _to_read(collection)


@router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Koleksiyonu sil (API tanımları silinmez)",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_collection(
    collection_id: int,
    _: Editor,
    use_case: Annotated[DeleteCollection, Depends(get_delete)],
) -> None:
    use_case(collection_id)


@router.get(
    "/{collection_id}/export",
    response_model=CollectionExport,
    summary="Koleksiyonu JSON olarak dışa aktar",
    description=(
        "API tanımları, adımlar, sıralama, kurallar ve değişken çıkarma ayarları dosyaya yazılır. "
        "Token, şifre gibi gizli değerler dosyaya YAZILMAZ; yerlerine {{token}} gibi "
        "yer tutucular konur ve required_variables listesinde belirtilir."
    ),
    responses=NOT_FOUND,
)
def export_collection(
    collection_id: int,
    _: CurrentUser,
    use_case: Annotated[ExportCollection, Depends(get_export)],
) -> CollectionExport:
    exported = use_case(collection_id)
    return CollectionExport(
        name=exported.name,
        description=exported.description,
        stop_on_failure=exported.stop_on_failure,
        apis=exported.apis,
        steps=exported.steps,
        required_variables=exported.required_variables,
    )


# --- Çalıştırma ---


@router.post(
    "/{collection_id}/run",
    response_model=CollectionRunRead,
    summary="Koleksiyonu çalıştır",
    description=(
        "Etkin adımları sırayla çalıştırır. Her adımda kurallar uygulanır ve cevaptan "
        "değişkenler alınır. stop_on_failure açıksa geçemeyen ilk adımdan sonra durur."
    ),
    responses={**NOT_FOUND, **FORBIDDEN, 409: {"description": "Production onayı gerekli"}},
)
def start_run(
    collection_id: int,
    user: Editor,
    use_case: Annotated[StartCollectionRun, Depends(get_start_run)],
    options: SendOptions | None = None,
) -> CollectionRunRead:
    options = options or SendOptions()
    details = use_case(
        collection_id,
        user=user,
        environment_id=options.environment_id,
        confirm_production=options.confirm_production,
    )
    return _run_read(details)


@router.post(
    "/{collection_id}/run-async",
    response_model=CollectionRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Koleksiyonu arka planda çalıştır (kuyruğa al)",
    description=(
        "Çalıştırmayı Celery kuyruğuna atar ve hemen döner (state=queued). Durumu "
        "GET /collections/{id}/runs/{run_id} ile izleyin: queued -> running -> completed. "
        "Her adım bittikçe steps listesi dolar."
    ),
    responses={
        **NOT_FOUND,
        **FORBIDDEN,
        409: {
            "description": "Production onayı gerekli",
            "content": {
                "application/json": {
                    "example": {"detail": {"code": PRODUCTION_CONFIRMATION, "message": "..."}}
                }
            },
        },
        503: {"description": "Kuyruğa eklenemedi"},
    },
)
def start_async_run(
    collection_id: int,
    user: Editor,
    use_case: Annotated[QueueCollectionRun, Depends(get_queue_run)],
    options: SendOptions | None = None,
) -> CollectionRunSummary:
    options = options or SendOptions()
    run = use_case(
        collection_id,
        user=user,
        environment_id=options.environment_id,
        confirm_production=options.confirm_production,
    )
    return CollectionRunSummary(**run_summary_fields(run))


@router.get(
    "/{collection_id}/runs",
    response_model=list[CollectionRunSummary],
    summary="Koleksiyonun son çalıştırmaları",
    responses=NOT_FOUND,
)
def list_collection_runs(
    collection_id: int,
    _: CurrentUser,
    use_case: Annotated[ListCollectionRuns, Depends(get_list_runs)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[CollectionRunSummary]:
    return [
        CollectionRunSummary(**run_summary_fields(run)) for run in use_case(collection_id, limit)
    ]


@router.get(
    "/{collection_id}/runs/{run_id}",
    response_model=CollectionRunRead,
    summary="Koleksiyon çalıştırma detayı",
    responses={404: {"description": "Kayıt bulunamadı"}},
)
def get_collection_run(
    collection_id: int,
    run_id: int,
    _: CurrentUser,
    use_case: Annotated[GetCollectionRun, Depends(get_get_run)],
) -> CollectionRunRead:
    return _run_read(use_case(collection_id, run_id))
