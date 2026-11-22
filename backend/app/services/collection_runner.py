"""Koleksiyon çalıştırma akışı (ATOP-38, ATOP-39).

Adımlar sırayla çalışır. Her adımdan sonra:
1. API'nin kuralları cevaba uygulanır (test motoru)
2. Adımın "değişken çıkarma" ayarlarıyla cevaptan değerler alınır ve sonraki adımlarda
   {{değişken}} olarak kullanılabilir (ortam değişkenleriyle aynı adı taşırsa onu ezer)
3. Sonuç test_runs tablosuna kaydedilir

stop_on_failure açıksa geçemeyen ilk adımdan sonra kalanlar "skipped" olur.
"""

import json
import time
from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_json
from app.models.collection import Collection, CollectionRun
from app.models.test_run import RunStatus
from app.models.user import User
from app.schemas.api_definition import MASK, SendResult
from app.schemas.assertion import AssertionResult, AssertionType
from app.schemas.collection import ExtractedValue, Extraction, StepResult
from app.services import http_runner, jsonpath
from app.services.assertions import evaluate
from app.services.test_runs import run_status, save_run

MAX_SHOWN_VALUE = 200
STEP_STATUSES = ("passed", "failed", "error", "skipped")
SOURCE_TYPES = {
    "json_path": AssertionType.JSON_PATH,
    "header": AssertionType.HEADER,
    "status_code": AssertionType.STATUS_CODE,
}


@dataclass
class RunContext:
    variables: dict[str, str] = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    environment_name: str | None = None


def extract_value(extraction: Extraction, result: SendResult) -> str | None:
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


def run_collection(
    db: Session,
    collection: Collection,
    context: RunContext,
    user: User | None,
    transport: httpx.BaseTransport | None = None,
) -> CollectionRun:
    started = time.perf_counter()
    variables = dict(context.variables)
    secrets = list(context.secrets)

    collection_run = CollectionRun(
        collection_id=collection.id,
        collection_name=collection.name,
        environment_name=context.environment_name,
        triggered_by_id=user.id if user else None,
        status=RunStatus.PASSED,
        steps=[],
    )
    db.add(collection_run)
    db.flush()  # id gerekiyor: adım kayıtları buna bağlanacak

    steps: list[StepResult] = []
    stop = False
    for item in collection.items:
        if not item.enabled:
            continue
        api = item.api
        api_name = api.name if api else "(silinmiş API)"
        method = api.method.value if api else "-"

        if stop:
            steps.append(
                StepResult(
                    position=item.position,
                    api_definition_id=item.api_definition_id,
                    api_name=api_name,
                    method=method,
                    status="skipped",
                    message="Önceki adım geçemediği için çalıştırılmadı",
                )
            )
            continue

        if api is None:
            steps.append(
                StepResult(
                    position=item.position,
                    api_definition_id=item.api_definition_id,
                    api_name=api_name,
                    method=method,
                    status="error",
                    message="Bu adımın API tanımı silinmiş",
                )
            )
            stop = collection.stop_on_failure
            continue

        try:
            auth = decrypt_json(api.auth_config_encrypted)
        except ValueError:
            auth = {}
        result = http_runner.send(
            api,
            auth,
            transport=transport,
            variables=variables,
            secret_values=secrets,
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
                        AssertionResult(
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

        test_run = save_run(db, api, result, rule_results, user, collection_run.id)
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

    counts = {name: sum(1 for step in steps if step.status == name) for name in STEP_STATUSES}
    collection_run.total_steps = len(steps)
    collection_run.passed_steps = counts["passed"]
    collection_run.failed_steps = counts["failed"] + counts["error"]
    collection_run.skipped_steps = counts["skipped"]
    collection_run.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    collection_run.steps = [step.model_dump(mode="json") for step in steps]
    if steps and counts["passed"] == len(steps):
        collection_run.status = RunStatus.PASSED
    elif counts["failed"]:
        collection_run.status = RunStatus.FAILED
    else:
        collection_run.status = RunStatus.ERROR if steps else RunStatus.PASSED

    db.commit()
    db.refresh(collection_run)
    return collection_run
