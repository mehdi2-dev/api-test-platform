"""Use case'ler: koleksiyon yönetimi, içe/dışa aktarma ve çalıştırma başlatma."""

from dataclasses import dataclass, field
from typing import Any

from app.application.errors import QueueUnavailable
from app.application.ports.api_definitions import ApiDefinitionRepository
from app.application.ports.collections import (
    CollectionRepository,
    CollectionRunRepository,
    RunQueue,
)
from app.application.ports.environments import EnvironmentRepository
from app.application.ports.security import Cipher
from app.application.ports.testing import ApiTestRunRepository
from app.application.use_cases.collection_runs import PrepareCollectionRun, RunCollection
from app.application.use_cases.environments import UNCHANGED, GetEnvironment, _Unchanged
from app.domain.api_definitions import SECRET_AUTH_FIELDS, ApiDefinition
from app.domain.collections import (
    Collection,
    CollectionRun,
    Extraction,
    RunState,
    StepInput,
)
from app.domain.errors import Conflict, InvalidInput, NotFound, SecretUnreadable
from app.domain.testing.runs import ApiTestRun
from app.domain.testing.variables import find_variables
from app.domain.users import User

QUEUE_ERROR = "Kuyruğa eklenemedi (Redis ve worker çalışıyor mu?)"
NO_ENABLED_STEPS = "Koleksiyonda çalıştırılacak etkin adım yok"


# --- Yönetim ---


def _ensure_name_free(
    collections: CollectionRepository, name: str, own_id: int | None = None
) -> None:
    other = collections.get_by_name(name)
    if other is not None and other.id != own_id:
        raise Conflict(f"'{name}' adında bir koleksiyon zaten var")


def _ensure_apis_exist(apis: ApiDefinitionRepository, steps: list[StepInput]) -> None:
    wanted = {step.api_definition_id for step in steps}
    missing = sorted(api_id for api_id in wanted if apis.get(api_id) is None)
    if missing:
        raise InvalidInput(f"API tanımı bulunamadı: {', '.join(map(str, missing))}")


@dataclass
class CollectionOverview:
    collection: Collection
    last_run: CollectionRun | None


class ListCollections:
    """Ada göre sıralı koleksiyonlar ve her birinin son çalıştırması."""

    def __init__(self, collections: CollectionRepository, runs: CollectionRunRepository) -> None:
        self._collections = collections
        self._runs = runs

    def __call__(self) -> list[CollectionOverview]:
        return [
            CollectionOverview(collection, self._runs.latest_for(collection.id))
            for collection in self._collections.list_all()
        ]


class GetCollection:
    def __init__(self, collections: CollectionRepository) -> None:
        self._collections = collections

    def __call__(self, collection_id: int) -> Collection:
        collection = self._collections.get(collection_id)
        if collection is None:
            raise NotFound("Koleksiyon bulunamadı")
        return collection


class CreateCollection:
    def __init__(self, collections: CollectionRepository, apis: ApiDefinitionRepository) -> None:
        self._collections = collections
        self._apis = apis

    def __call__(
        self,
        *,
        created_by: User,
        name: str,
        description: str | None,
        stop_on_failure: bool,
        steps: list[StepInput],
    ) -> Collection:
        _ensure_name_free(self._collections, name)
        _ensure_apis_exist(self._apis, steps)
        collection = Collection(
            name=name,
            description=description,
            stop_on_failure=stop_on_failure,
            created_by_id=created_by.id,
        )
        collection.replace_items(steps)
        self._collections.save(collection)
        return collection


class UpdateCollection:
    """Sadece verilen alanlar değişir; steps verilirse adımların tamamı ve sırası yenilenir."""

    def __init__(self, collections: CollectionRepository, apis: ApiDefinitionRepository) -> None:
        self._collections = collections
        self._apis = apis

    def __call__(
        self,
        collection_id: int,
        *,
        name: str | None = None,
        description: str | None | _Unchanged = UNCHANGED,
        stop_on_failure: bool | None = None,
        steps: list[StepInput] | None = None,
    ) -> Collection:
        collection = GetCollection(self._collections)(collection_id)
        if name is not None:
            _ensure_name_free(self._collections, name, own_id=collection.id)
            collection.name = name
        if not isinstance(description, _Unchanged):
            collection.description = description
        if stop_on_failure is not None:
            collection.stop_on_failure = stop_on_failure
        if steps is not None:
            _ensure_apis_exist(self._apis, steps)
            collection.replace_items(steps)
        self._collections.save(collection)
        return collection


class DeleteCollection:
    """Koleksiyonu siler; API tanımları silinmez."""

    def __init__(self, collections: CollectionRepository) -> None:
        self._collections = collections

    def __call__(self, collection_id: int) -> None:
        self._collections.delete(GetCollection(self._collections)(collection_id))


# --- Dışa aktarma ---


@dataclass
class ExportedCollection:
    """Dosyaya yazılacak koleksiyon: API'ler, adımlar ve ortama eklenmesi gereken değişkenler.

    Token, şifre gibi gizli değerler yazılmaz; yerlerine {{token}} gibi yer tutucular konur.
    """

    name: str
    description: str | None
    stop_on_failure: bool
    apis: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    required_variables: list[str] = field(default_factory=list)


def _used_variables(exported: dict[str, Any]) -> set[str]:
    texts = [exported["url"], exported["body"] or ""]
    for row in [*exported["headers"], *exported["query_params"]]:
        texts += [str(row.get("key", "")), str(row.get("value", ""))]
    texts += [str(value) for value in exported["auth"].values()]
    for rule in exported["assertions"]:
        texts += [str(rule.get("target") or ""), str(rule.get("expected") or "")]
    names: set[str] = set()
    for text in texts:
        names |= find_variables(text)
    return names


class ExportCollection:
    def __init__(self, collections: CollectionRepository, cipher: Cipher) -> None:
        self._collections = collections
        self._cipher = cipher

    def _export_api(self, api: ApiDefinition) -> tuple[dict[str, Any], set[str]]:
        try:
            stored = api.stored_auth(self._cipher.decrypt)
        except SecretUnreadable:
            stored = {}
        auth: dict[str, Any] = {"type": api.auth_type.value, **stored}
        placeholders: set[str] = set()
        for secret in SECRET_AUTH_FIELDS:
            value = auth.get(secret)
            if value and "{{" not in value:
                auth[secret] = "{{" + secret + "}}"
                placeholders.add(secret)
        exported = {
            "name": api.name,
            "description": api.description,
            "method": api.method.value,
            "url": api.url,
            "headers": api.headers or [],
            "query_params": api.query_params or [],
            "body_type": api.body_type.value,
            "body": api.body,
            "auth": auth,
            "assertions": api.assertions or [],
        }
        return exported, placeholders

    def __call__(self, collection_id: int) -> ExportedCollection:
        collection = GetCollection(self._collections)(collection_id)
        result = ExportedCollection(
            name=collection.name,
            description=collection.description,
            stop_on_failure=collection.stop_on_failure,
        )
        index_of: dict[int, int] = {}
        used: set[str] = set()
        extracted: set[str] = set()

        for item in collection.items:
            if item.api is None:
                continue
            if item.api_definition_id not in index_of:
                exported, placeholders = self._export_api(item.api)
                index_of[item.api_definition_id] = len(result.apis)
                result.apis.append(exported)
                used |= placeholders | _used_variables(exported)
            extractions = item.extractions or []
            extracted |= {Extraction.from_dict(raw).variable for raw in extractions}
            result.steps.append(
                {
                    "api": index_of[item.api_definition_id],
                    "enabled": item.enabled,
                    "extractions": extractions,
                }
            )

        # Adımlarda cevaptan alınan değişkenleri ortamda tanımlamaya gerek yok
        result.required_variables = sorted(used - extracted)
        return result


# --- İçe aktarma ---


@dataclass
class ImportedApi:
    """Doğrulanmış, içe aktarılacak API tanımı (auth_fields şifrelenmemiş)."""

    name: str
    description: str | None
    method: Any
    url: str
    headers: list[dict[str, Any]]
    query_params: list[dict[str, Any]]
    body_type: Any
    body: str | None
    assertions: list[dict[str, Any]]
    auth_type: Any
    auth_fields: dict[str, Any]


@dataclass
class ImportedStep:
    api: int
    """apis listesindeki sıra numarası"""
    enabled: bool = True
    extractions: list[dict[str, Any]] = field(default_factory=list)


class ImportCollection:
    """Dışa aktarılmış koleksiyondan API tanımlarını ve koleksiyonu oluşturur.

    Aynı adda koleksiyon varsa adın sonuna (2), (3)... eklenir.
    """

    def __init__(
        self,
        collections: CollectionRepository,
        apis: ApiDefinitionRepository,
        cipher: Cipher,
    ) -> None:
        self._collections = collections
        self._apis = apis
        self._cipher = cipher

    def __call__(
        self,
        *,
        name: str,
        description: str | None,
        stop_on_failure: bool,
        apis: list[ImportedApi],
        steps: list[ImportedStep],
        user_id: int | None,
    ) -> tuple[Collection, int]:
        unique_name = name
        suffix = 2
        while self._collections.get_by_name(unique_name) is not None:
            unique_name = f"{name[:140]} ({suffix})"
            suffix += 1

        created: list[ApiDefinition] = []
        for item in apis:
            api = ApiDefinition(
                name=item.name,
                description=item.description,
                method=item.method,
                url=item.url,
                headers=item.headers,
                query_params=item.query_params,
                body_type=item.body_type,
                body=item.body,
                assertions=item.assertions,
                created_by_id=user_id,
            )
            api.change_auth(
                item.auth_type,
                item.auth_fields,
                encrypt=self._cipher.encrypt,
                decrypt=self._cipher.decrypt,
            )
            self._apis.save(api)  # adımlarda id'leri kullanılacak
            created.append(api)

        collection = Collection(
            name=unique_name,
            description=description,
            stop_on_failure=stop_on_failure,
            created_by_id=user_id,
        )
        collection.replace_items(
            [
                StepInput(
                    api_definition_id=created[step.api].id,
                    enabled=step.enabled,
                    extractions=step.extractions,
                )
                for step in steps
            ]
        )
        self._collections.save(collection)
        return collection, len(created)


# --- Çalıştırma ---


@dataclass
class CollectionRunDetails:
    run: CollectionRun
    step_runs: list[ApiTestRun]


def _runnable(
    collections: CollectionRepository,
    environments: EnvironmentRepository,
    collection_id: int,
    environment_id: int | None,
) -> Collection:
    """Koleksiyon var mı, etkin adımı var mı, seçilen ortam var mı?"""
    collection = GetCollection(collections)(collection_id)
    if not collection.enabled_items:
        raise InvalidInput(NO_ENABLED_STEPS)
    if environment_id is not None:
        GetEnvironment(environments)(environment_id)
    return collection


class StartCollectionRun:
    """Koleksiyonu hemen çalıştırır ve sonucu döndürür."""

    def __init__(
        self,
        collections: CollectionRepository,
        environments: EnvironmentRepository,
        prepare: PrepareCollectionRun,
        run_collection: RunCollection,
        test_runs: ApiTestRunRepository,
    ) -> None:
        self._collections = collections
        self._environments = environments
        self._prepare = prepare
        self._run_collection = run_collection
        self._test_runs = test_runs

    def __call__(
        self,
        collection_id: int,
        *,
        user: User,
        environment_id: int | None = None,
        confirm_production: bool = False,
    ) -> CollectionRunDetails:
        collection = _runnable(self._collections, self._environments, collection_id, environment_id)
        context = self._prepare(collection, environment_id, confirm_production)
        run = self._run_collection(collection, context, user.id)
        return CollectionRunDetails(run, self._test_runs.for_collection_run(run.id))


class QueueCollectionRun:
    """Çalıştırmayı kuyruğa atar ve hemen döner (state=queued); worker yürütür.

    Ortam ve Production kontrolü şimdi yapılır ki hata kullanıcıya hemen dönsün.
    """

    def __init__(
        self,
        collections: CollectionRepository,
        environments: EnvironmentRepository,
        prepare: PrepareCollectionRun,
        runs: CollectionRunRepository,
        queue: RunQueue,
    ) -> None:
        self._collections = collections
        self._environments = environments
        self._prepare = prepare
        self._runs = runs
        self._queue = queue

    def __call__(
        self,
        collection_id: int,
        *,
        user: User,
        environment_id: int | None = None,
        confirm_production: bool = False,
    ) -> CollectionRun:
        collection = _runnable(self._collections, self._environments, collection_id, environment_id)
        context = self._prepare(collection, environment_id, confirm_production)
        run = CollectionRun.new(
            collection,
            RunState.QUEUED,
            user_id=user.id,
            environment_name=context.environment_name,
        )
        self._runs.save(run)  # worker kaydı bulabilsin diye kuyruğa atmadan önce kaydet

        try:
            self._queue.enqueue(run.id, environment_id, confirm_production)
        except Exception as exc:
            run.fail(QUEUE_ERROR)
            self._runs.save(run)
            raise QueueUnavailable(QUEUE_ERROR) from exc
        return run


class ListCollectionRuns:
    def __init__(self, collections: CollectionRepository, runs: CollectionRunRepository) -> None:
        self._collections = collections
        self._runs = runs

    def __call__(self, collection_id: int, limit: int) -> list[CollectionRun]:
        GetCollection(self._collections)(collection_id)
        return self._runs.recent_for(collection_id, limit)


class GetCollectionRun:
    def __init__(self, runs: CollectionRunRepository, test_runs: ApiTestRunRepository) -> None:
        self._runs = runs
        self._test_runs = test_runs

    def __call__(self, collection_id: int, run_id: int) -> CollectionRunDetails:
        run = self._runs.get(run_id)
        if run is None or run.collection_id != collection_id:
            raise NotFound("Kayıt bulunamadı")
        return CollectionRunDetails(run, self._test_runs.for_collection_run(run.id))
