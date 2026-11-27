"""Koleksiyon çalıştırma akışı (ATOP-38, ATOP-39, ATOP-41, ATOP-44).

Adımlar sırayla çalışır. Her adımdan sonra:
1. API'nin kuralları cevaba uygulanır (test motoru)
2. Adımın "değişken çıkarma" ayarlarıyla cevaptan değerler alınır ve sonraki adımlarda
   {{değişken}} olarak kullanılabilir (ortam değişkenleriyle aynı adı taşırsa onu ezer)
3. Sonuç test_runs tablosuna kaydedilir ve çalıştırma kaydı güncellenir; böylece
   arayüz çalışma sürerken ilerlemeyi (1/3, 2/3...) canlı görebilir

stop_on_failure açıksa geçemeyen ilk adımdan sonra kalanlar "skipped" olur.

İki yoldan çalışır:
- Senkron:  POST /collections/{id}/run          -> run_collection() hemen çalışır
- Asenkron: POST /collections/{id}/run-async    -> "queued" kayıt oluşur, Celery worker
            execute_collection_run() ile çalıştırır (zamanlanmış çalıştırmalar da böyle)
"""

import json
import logging
import time
from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session

from app.adapters.outbound.http.sender import HttpxApiSender
from app.api.environments import variable_values
from app.core.crypto import decrypt_json
from app.domain.testing import jsonpath
from app.domain.testing.engine import evaluate
from app.domain.testing.rules import AssertionType, RuleResult
from app.domain.testing.runs import SendOutcome
from app.models.api_definition import HttpMethod
from app.models.collection import Collection, CollectionRun, RunState, RunTrigger
from app.models.environment import Environment
from app.models.test_run import RunStatus
from app.schemas.api_definition import MASK
from app.schemas.collection import ExtractedValue, Extraction, StepResult
from app.services.test_runs import run_status, save_run

logger = logging.getLogger(__name__)

MAX_SHOWN_VALUE = 200
STEP_STATUSES = ("passed", "failed", "error", "skipped")
SOURCE_TYPES = {
    "json_path": AssertionType.JSON_PATH,
    "header": AssertionType.HEADER,
    "status_code": AssertionType.STATUS_CODE,
}
MUTATING_METHODS = {HttpMethod.POST, HttpMethod.PUT, HttpMethod.PATCH, HttpMethod.DELETE}


@dataclass
class RunContext:
    variables: dict[str, str] = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    environment_name: str | None = None


class RunPreparationError(Exception):
    """Çalıştırma başlayamadı (ortam yok, production onayı yok...)."""


class EnvironmentNotFound(RunPreparationError):
    pass


class ProductionConfirmationRequired(RunPreparationError):
    pass


def build_context(
    db: Session, collection: Collection, environment_id: int | None, confirm_production: bool
) -> RunContext:
    """Ortam değişkenlerini yükler ve Production kuralını uygular (ATOP-30)."""
    context = RunContext()
    if environment_id is None:
        return context

    environment = db.get(Environment, environment_id)
    if environment is None:
        raise EnvironmentNotFound("Ortam bulunamadı")
    context.environment_name = environment.name
    context.variables, context.secrets = variable_values(environment)

    if environment.is_production and not confirm_production:
        risky = [
            f"{item.api.method.value} {item.api.name}"
            for item in collection.items
            if item.enabled and item.api and item.api.method in MUTATING_METHODS
        ]
        if risky:
            raise ProductionConfirmationRequired(
                f"'{environment.name}' bir Production ortamı ve koleksiyonda veri "
                f"değiştirebilecek adımlar var: {', '.join(risky)}. Emin misiniz?"
            )
    return context


def extract_value(extraction: Extraction, result: SendOutcome) -> str | None:
    """Cevaptan değeri metin olarak döndürür; bulunamazsa None."""
    if not result.ok or result.status_code is None:
        return None
    if extraction.source == "status_code":
        return str(result.status_code)
    if extraction.source == "header":
        lowered = {key.lower(): value for key, value in result.headers.items()}
        return lowered.get((extraction.path or "").lower())

    is_json = result.body_json is not None or result.body.strip() == "null"
    if not is_json:
        return None
    value = jsonpath.extract(result.body_json, extraction.path or "$")
    if value is jsonpath.MISSING:
        return None
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _shown(value: str, secret: bool) -> str:
    if secret:
        return MASK
    return value if len(value) <= MAX_SHOWN_VALUE else value[:MAX_SHOWN_VALUE] + "…"


def new_run(
    collection: Collection,
    state: RunState,
    trigger: RunTrigger = RunTrigger.MANUAL,
    user_id: int | None = None,
    environment_name: str | None = None,
    schedule_id: int | None = None,
) -> CollectionRun:
    return CollectionRun(
        collection_id=collection.id,
        collection_name=collection.name,
        environment_name=environment_name,
        triggered_by_id=user_id,
        state=state.value,
        trigger=trigger.value,
        schedule_id=schedule_id,
        status=None,
        total_steps=sum(1 for item in collection.items if item.enabled),
        passed_steps=0,
        failed_steps=0,
        skipped_steps=0,
        elapsed_ms=0,
        steps=[],
    )


def finish_with_error(db: Session, collection_run: CollectionRun, message: str) -> CollectionRun:
    collection_run.state = RunState.COMPLETED.value
    collection_run.status = RunStatus.ERROR
    collection_run.error = message
    db.commit()
    db.refresh(collection_run)
    return collection_run


def _record_progress(collection_run: CollectionRun, steps: list[StepResult]) -> None:
    counts = {name: sum(1 for step in steps if step.status == name) for name in STEP_STATUSES}
    collection_run.passed_steps = counts["passed"]
    collection_run.failed_steps = counts["failed"] + counts["error"]
    collection_run.skipped_steps = counts["skipped"]
    collection_run.steps = [step.model_dump(mode="json") for step in steps]


def run_collection(
    db: Session,
    collection: Collection,
    context: RunContext,
    user_id: int | None,
    transport: httpx.BaseTransport | None = None,
    collection_run: CollectionRun | None = None,
) -> CollectionRun:
    """Koleksiyonu baştan sona çalıştırır. collection_run verilirse (kuyruktan gelen) onu
    günceller, verilmezse yeni bir kayıt oluşturur."""
    started = time.perf_counter()
    variables = dict(context.variables)
    secrets = list(context.secrets)

    if collection_run is None:
        collection_run = new_run(collection, RunState.RUNNING, user_id=user_id)
        db.add(collection_run)
    collection_run.state = RunState.RUNNING.value
    collection_run.environment_name = context.environment_name
    collection_run.total_steps = sum(1 for item in collection.items if item.enabled)
    db.commit()  # id gerekiyor ve arayüz "çalışıyor" durumunu görsün

    steps: list[StepResult] = []
    stop = False
    for item in collection.items:
        if not item.enabled:
            continue
        api = item.api
        api_name = api.name if api else "(silinmiş API)"
        method = api.method.value if api else "-"

        if stop or api is None:
            steps.append(
                StepResult(
                    position=item.position,
                    api_definition_id=item.api_definition_id,
                    api_name=api_name,
                    method=method,
                    status="skipped" if stop else "error",
                    message=(
                        "Önceki adım geçemediği için çalıştırılmadı"
                        if stop
                        else "Bu adımın API tanımı silinmiş"
                    ),
                )
            )
            stop = stop or collection.stop_on_failure
            _record_progress(collection_run, steps)
            db.commit()
            continue

        try:
            auth = decrypt_json(api.auth_config_encrypted)
        except ValueError:
            auth = {}
        result = HttpxApiSender(transport).send(
            api,
            auth,
            variables=variables,
            secrets=secrets,
            environment_name=context.environment_name,
        )
        rule_results = evaluate(api.assertions or [], result, variables)

        # Cevaptan değişken çıkar; bulunamayan değer adımı "kaldı" yapar
        extracted: list[ExtractedValue] = []
        for raw in item.extractions or []:
            extraction = Extraction.model_validate(raw)
            value = extract_value(extraction, result)
            if value is None:
                extracted.append(ExtractedValue(variable=extraction.variable, found=False))
                if result.ok:
                    rule_results.append(
                        RuleResult(
                            type=SOURCE_TYPES[extraction.source],
                            target=extraction.path,
                            operator="extract",
                            expected=f"{{{{{extraction.variable}}}}}",
                            passed=False,
                            message=f"'{extraction.variable}' değişkeni cevaptan alınamadı",
                        )
                    )
                continue
            variables[extraction.variable] = value
            if extraction.secret and value:
                secrets.append(value)
            extracted.append(
                ExtractedValue(
                    variable=extraction.variable,
                    found=True,
                    value=_shown(value, extraction.secret),
                )
            )

        test_run = save_run(db, api, result, rule_results, user_id, collection_run.id, secrets)
        status = run_status(result, rule_results).value
        steps.append(
            StepResult(
                position=item.position,
                api_definition_id=api.id,
                api_name=api.name,
                method=method,
                status=status,
                test_run_id=test_run.id,
                message=result.error,
                extracted=extracted,
            )
        )
        if status != "passed" and collection.stop_on_failure:
            stop = True
        _record_progress(collection_run, steps)
        db.commit()  # canlı izleme: her adımdan sonra ilerleme görünsün

    counts = {name: sum(1 for step in steps if step.status == name) for name in STEP_STATUSES}
    collection_run.total_steps = len(steps)
    collection_run.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    _record_progress(collection_run, steps)
    if steps and counts["passed"] == len(steps):
        collection_run.status = RunStatus.PASSED
    elif counts["failed"]:
        collection_run.status = RunStatus.FAILED
    else:
        collection_run.status = RunStatus.ERROR if steps else RunStatus.PASSED
    collection_run.state = RunState.COMPLETED.value

    db.commit()
    db.refresh(collection_run)
    _notify_safely(db, collection_run, transport)
    return collection_run


def _notify_safely(
    db: Session, collection_run: CollectionRun, transport: httpx.BaseTransport | None
) -> None:
    """Bildirim gönder (ATOP-48); bildirimdeki bir sorun çalıştırmanın sonucunu bozmasın."""
    from app.services.notifications import notify_collection_run

    try:
        notify_collection_run(db, collection_run, transport)
    except Exception:
        logger.exception("Bildirimler gönderilemedi: çalıştırma %s", collection_run.id)
        db.rollback()


def execute_collection_run(
    db: Session,
    collection_run_id: int,
    environment_id: int | None,
    confirm_production: bool,
    transport: httpx.BaseTransport | None = None,
) -> CollectionRun | None:
    """Kuyruktaki bir çalıştırmayı yürütür (Celery worker bunu çağırır, ATOP-41).

    Aynı kayıt iki kez gelirse (ör. worker yeniden başladı) ikinci sefer bir şey yapmaz.
    """
    collection_run = db.get(CollectionRun, collection_run_id)
    if collection_run is None:
        logger.warning("Çalıştırma kaydı bulunamadı: %s", collection_run_id)
        return None
    if collection_run.state != RunState.QUEUED.value:
        return collection_run

    collection = (
        db.get(Collection, collection_run.collection_id) if collection_run.collection_id else None
    )
    if collection is None:
        return finish_with_error(db, collection_run, "Koleksiyon silinmiş")

    try:
        context = build_context(db, collection, environment_id, confirm_production)
    except RunPreparationError as exc:
        collection_run = finish_with_error(db, collection_run, str(exc))
        _notify_safely(db, collection_run, transport)
        return collection_run

    try:
        return run_collection(
            db,
            collection,
            context,
            collection_run.triggered_by_id,
            transport=transport,
            collection_run=collection_run,
        )
    except Exception as exc:  # worker çökmesin, kayıt "çalışıyor"da takılı kalmasın
        logger.exception("Koleksiyon çalıştırması başarısız: %s", collection_run_id)
        db.rollback()
        collection_run = db.get(CollectionRun, collection_run_id)
        collection_run = finish_with_error(db, collection_run, f"Beklenmeyen hata: {exc}")
        _notify_safely(db, collection_run, transport)
        return collection_run
