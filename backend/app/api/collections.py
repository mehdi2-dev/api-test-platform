"""Koleksiyonlar: oluşturma, sıralama, çalıştırma, içe/dışa aktarma (ATOP-37..40).

Yetkiler:
- Herkes (giriş yapmış): koleksiyonları, çalıştırma sonuçlarını görür, dışa aktarır
- Admin ve Tester: oluşturur, değiştirir, siler, çalıştırır, içe aktarır
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import select

from app.api.apis import PRODUCTION_CONFIRMATION, HttpTransport
from app.api.deps import CurrentUser, DbSession, require_roles
from app.api.environments import get_environment_or_404
from app.core.crypto import decrypt_json, encrypt_json
from app.models.api_definition import ApiDefinition, AuthType
from app.models.collection import Collection, CollectionItem, CollectionRun
from app.models.test_run import ApiTestRun
from app.models.user import Role, User
from app.schemas.api_definition import MASK, SECRET_FIELDS, ApiDefinitionCreate
from app.schemas.collection import (
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
    ExportedApi,
    ExportedStep,
    Extraction,
    ImportResult,
    StepResult,
)
from app.schemas.environment import SendOptions
from app.services.collection_runner import (
    ProductionConfirmationRequired,
    RunContext,
    RunState,
    build_context,
    finish_with_error,
    new_run,
    run_collection,
)
from app.services.scheduler import QUEUE_ERROR, Enqueue, celery_enqueue
from app.services.test_runs import run_to_read
from app.services.variables import find_variables

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


# --- Yardımcılar ---


def _get_or_404(db: DbSession, collection_id: int) -> Collection:
    collection = db.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Koleksiyon bulunamadı")
    return collection


def _check_name_free(db: DbSession, name: str, own_id: int | None = None) -> None:
    other = db.scalar(select(Collection).where(Collection.name == name))
    if other is not None and other.id != own_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"'{name}' adında bir koleksiyon zaten var"
        )


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


def _set_items(db: DbSession, collection: Collection, items: list[CollectionItemIn]) -> None:
    """Adımları verilen sırayla yeniden oluşturur (sürükle-bırak sonrası sıra buradan gelir)."""
    wanted = {item.api_definition_id for item in items}
    found = set(db.scalars(select(ApiDefinition.id).where(ApiDefinition.id.in_(wanted))))
    missing = sorted(wanted - found)
    if missing:
        raise HTTPException(422, detail=f"API tanımı bulunamadı: {', '.join(map(str, missing))}")

    collection.items = [
        CollectionItem(
            api_definition_id=item.api_definition_id,
            position=index,
            enabled=item.enabled,
            extractions=[extraction.model_dump() for extraction in item.extractions],
        )
        for index, item in enumerate(items)
    ]


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


def _run_read(db: DbSession, run: CollectionRun) -> CollectionRunRead:
    step_runs = db.scalars(select(ApiTestRun).where(ApiTestRun.collection_run_id == run.id))
    return CollectionRunRead(
        **run_summary_fields(run),
        steps=[StepResult.model_validate(step) for step in run.steps or []],
        step_runs={test_run.id: run_to_read(test_run) for test_run in step_runs},
    )


# --- CRUD (ATOP-37) ---


@router.get("", response_model=list[CollectionSummary], summary="Koleksiyonları listele")
def list_collections(_: CurrentUser, db: DbSession) -> list[CollectionSummary]:
    summaries = []
    for collection in db.scalars(select(Collection).order_by(Collection.name)):
        last = db.scalar(
            select(CollectionRun)
            .where(CollectionRun.collection_id == collection.id)
            .order_by(CollectionRun.created_at.desc(), CollectionRun.id.desc())
            .limit(1)
        )
        summaries.append(
            CollectionSummary(
                id=collection.id,
                name=collection.name,
                description=collection.description,
                stop_on_failure=collection.stop_on_failure,
                item_count=len(collection.items),
                last_run_status=last.status if last else None,
                last_run_at=last.created_at if last else None,
                updated_at=collection.updated_at,
            )
        )
    return summaries


@router.post(
    "",
    response_model=CollectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni koleksiyon",
    responses={**FORBIDDEN, **CONFLICT},
)
def create_collection(body: CollectionCreate, user: Editor, db: DbSession) -> CollectionRead:
    _check_name_free(db, body.name)
    collection = Collection(
        name=body.name,
        description=body.description,
        stop_on_failure=body.stop_on_failure,
        created_by_id=user.id,
    )
    _set_items(db, collection, body.items)
    db.add(collection)
    db.commit()
    db.refresh(collection)
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
def import_collection(body: CollectionExport, user: Editor, db: DbSession) -> ImportResult:
    collection, created = create_from_export(db, body, user.id)
    return ImportResult(
        collection=_to_read(collection),
        created_apis=created,
        required_variables=body.required_variables,
    )


def create_from_export(
    db: DbSession, body: CollectionExport, user_id: int | None
) -> tuple[Collection, int]:
    """Dışa aktarılmış JSON'dan API tanımlarını ve koleksiyonu oluşturur."""
    name = body.name
    suffix = 2
    while db.scalar(select(Collection.id).where(Collection.name == name)) is not None:
        name = f"{body.name[:140]} ({suffix})"
        suffix += 1

    created: list[ApiDefinition] = []
    for index, exported in enumerate(body.apis, start=1):
        try:
            definition = ApiDefinitionCreate.model_validate(exported.model_dump())
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(part) for part in first["loc"])
            raise HTTPException(
                422, detail=f"{index}. API ({exported.name}) geçersiz: {where}: {first['msg']}"
            ) from exc
        fields = definition.auth.stored_fields()
        if any(fields.get(secret) == MASK for secret in SECRET_FIELDS):
            raise HTTPException(
                422, detail=f"{index}. API ({exported.name}): maskeli gizli değer içe aktarılamaz"
            )
        api = ApiDefinition(
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
            auth_config_encrypted=(
                encrypt_json(fields) if definition.auth.type != AuthType.NONE else None
            ),
            created_by_id=user_id,
        )
        db.add(api)
        created.append(api)
    db.flush()  # API'lerin id'leri adımlarda kullanılacak

    collection = Collection(
        name=name,
        description=body.description,
        stop_on_failure=body.stop_on_failure,
        created_by_id=user_id,
        items=[
            CollectionItem(
                api_definition_id=created[step.api].id,
                position=position,
                enabled=step.enabled,
                extractions=[extraction.model_dump() for extraction in step.extractions],
            )
            for position, step in enumerate(body.steps)
        ],
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection, len(created)


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
    from app.services.demo_seed import seed_demo

    return seed_demo(db, user.id)


@router.get(
    "/{collection_id}",
    response_model=CollectionRead,
    summary="Koleksiyon detayı",
    responses=NOT_FOUND,
)
def get_collection(collection_id: int, _: CurrentUser, db: DbSession) -> CollectionRead:
    return _to_read(_get_or_404(db, collection_id))


@router.patch(
    "/{collection_id}",
    response_model=CollectionRead,
    summary="Koleksiyonu güncelle (adımlar ve sıraları dahil)",
    responses={**NOT_FOUND, **FORBIDDEN, **CONFLICT},
)
def update_collection(
    collection_id: int, body: CollectionUpdate, _: Editor, db: DbSession
) -> CollectionRead:
    collection = _get_or_404(db, collection_id)
    if body.name is not None:
        _check_name_free(db, body.name, own_id=collection.id)
        collection.name = body.name
    if "description" in body.model_fields_set:
        collection.description = body.description
    if body.stop_on_failure is not None:
        collection.stop_on_failure = body.stop_on_failure
    if body.items is not None:
        _set_items(db, collection, body.items)
    db.commit()
    db.refresh(collection)
    return _to_read(collection)


@router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Koleksiyonu sil (API tanımları silinmez)",
    responses={**NOT_FOUND, **FORBIDDEN},
)
def delete_collection(collection_id: int, _: Editor, db: DbSession) -> None:
    db.delete(_get_or_404(db, collection_id))
    db.commit()


# --- Dışa aktarma (ATOP-40) ---


def _export_api(api: ApiDefinition) -> tuple[ExportedApi, set[str]]:
    """API'yi dışa aktarılacak hale getirir. Gizli değerler {{alan}} yer tutucusuyla değişir."""
    try:
        stored = decrypt_json(api.auth_config_encrypted)
    except ValueError:
        stored = {}
    auth: dict[str, Any] = {"type": api.auth_type.value, **stored}
    placeholders: set[str] = set()
    for secret in SECRET_FIELDS:
        value = auth.get(secret)
        if value and "{{" not in value:
            auth[secret] = "{{" + secret + "}}"
            placeholders.add(secret)

    exported = ExportedApi(
        name=api.name,
        description=api.description,
        method=api.method.value,
        url=api.url,
        headers=api.headers or [],
        query_params=api.query_params or [],
        body_type=api.body_type.value,
        body=api.body,
        auth=auth,
        assertions=api.assertions or [],
    )
    return exported, placeholders


def _used_variables(exported: ExportedApi) -> set[str]:
    texts = [exported.url, exported.body or ""]
    for row in [*exported.headers, *exported.query_params]:
        texts += [str(row.get("key", "")), str(row.get("value", ""))]
    texts += [str(value) for value in exported.auth.values()]
    for rule in exported.assertions:
        texts += [str(rule.get("target") or ""), str(rule.get("expected") or "")]
    names: set[str] = set()
    for text in texts:
        names |= find_variables(text)
    return names


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
def export_collection(collection_id: int, _: CurrentUser, db: DbSession) -> CollectionExport:
    collection = _get_or_404(db, collection_id)

    apis: list[ExportedApi] = []
    index_of: dict[int, int] = {}
    used: set[str] = set()
    steps: list[ExportedStep] = []
    extracted: set[str] = set()

    for item in collection.items:
        if item.api is None:
            continue
        if item.api_definition_id not in index_of:
            exported, placeholders = _export_api(item.api)
            index_of[item.api_definition_id] = len(apis)
            apis.append(exported)
            used |= placeholders | _used_variables(exported)
        extractions = [Extraction.model_validate(raw) for raw in item.extractions or []]
        extracted |= {extraction.variable for extraction in extractions}
        steps.append(
            ExportedStep(
                api=index_of[item.api_definition_id],
                enabled=item.enabled,
                extractions=extractions,
            )
        )

    return CollectionExport(
        name=collection.name,
        description=collection.description,
        stop_on_failure=collection.stop_on_failure,
        apis=apis,
        steps=steps,
        # Adımlarda cevaptan alınan değişkenleri ortamda tanımlamaya gerek yok
        required_variables=sorted(used - extracted),
    )


# --- Çalıştırma (ATOP-38, ATOP-39) ---


def _context(db: DbSession, collection: Collection, options: SendOptions) -> RunContext:
    """Ortamı ve Production kuralını kontrol eder; sorun varsa HTTP hatası döner."""
    if options.environment_id is not None:
        get_environment_or_404(db, options.environment_id)
    try:
        return build_context(db, collection, options.environment_id, options.confirm_production)
    except ProductionConfirmationRequired as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": PRODUCTION_CONFIRMATION, "message": str(exc)},
        ) from exc


def _require_steps(collection: Collection) -> None:
    if not any(item.enabled for item in collection.items):
        raise HTTPException(422, detail="Koleksiyonda çalıştırılacak etkin adım yok")


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
    db: DbSession,
    transport: HttpTransport,
    options: SendOptions | None = None,
) -> CollectionRunRead:
    collection = _get_or_404(db, collection_id)
    _require_steps(collection)
    context = _context(db, collection, options or SendOptions())
    collection_run = run_collection(db, collection, context, user.id, transport)
    return _run_read(db, collection_run)


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
        409: {"description": "Production onayı gerekli"},
        503: {"description": "Kuyruğa eklenemedi"},
    },
)
def start_async_run(
    collection_id: int,
    user: Editor,
    db: DbSession,
    enqueue: Enqueuer,
    options: SendOptions | None = None,
) -> CollectionRunSummary:
    options = options or SendOptions()
    collection = _get_or_404(db, collection_id)
    _require_steps(collection)
    context = _context(db, collection, options)  # ortam ve Production kontrolü şimdi

    collection_run = new_run(
        collection,
        RunState.QUEUED,
        user_id=user.id,
        environment_name=context.environment_name,
    )
    db.add(collection_run)
    db.commit()  # worker kaydı bulabilsin diye kuyruğa atmadan önce kaydet
    db.refresh(collection_run)

    try:
        enqueue(collection_run.id, options.environment_id, options.confirm_production)
    except Exception as exc:
        finish_with_error(db, collection_run, QUEUE_ERROR)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=QUEUE_ERROR) from exc

    db.refresh(collection_run)
    return CollectionRunSummary(**run_summary_fields(collection_run))


@router.get(
    "/{collection_id}/runs",
    response_model=list[CollectionRunSummary],
    summary="Koleksiyonun son çalıştırmaları",
    responses=NOT_FOUND,
)
def list_collection_runs(
    collection_id: int,
    _: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[CollectionRunSummary]:
    _get_or_404(db, collection_id)
    query = (
        select(CollectionRun)
        .where(CollectionRun.collection_id == collection_id)
        .order_by(CollectionRun.created_at.desc(), CollectionRun.id.desc())
        .limit(limit)
    )
    return [CollectionRunSummary(**run_summary_fields(run)) for run in db.scalars(query)]


@router.get(
    "/{collection_id}/runs/{run_id}",
    response_model=CollectionRunRead,
    summary="Koleksiyon çalıştırma detayı",
    responses={404: {"description": "Kayıt bulunamadı"}},
)
def get_collection_run(
    collection_id: int, run_id: int, _: CurrentUser, db: DbSession
) -> CollectionRunRead:
    collection_run = db.get(CollectionRun, run_id)
    if collection_run is None or collection_run.collection_id != collection_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı")
    return _run_read(db, collection_run)
