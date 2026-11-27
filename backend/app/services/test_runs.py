"""Test çalıştırma sonuçlarını kaydetme ve okuma (ATOP-35).

Saklanan istek/cevap/kural sonuçlarında gizli değerler maskelenir (ATOP-50).
"""

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.domain.testing.masking import is_sensitive_path, mask_headers, mask_text
from app.domain.testing.rules import RuleResult
from app.domain.testing.variables import mask_secrets
from app.models.api_definition import ApiDefinition
from app.models.test_run import ApiTestRun, RunStatus
from app.schemas.api_definition import MASK, SendResult
from app.schemas.assertion import TestRunRead, TestRunSummary

# Veritabanında saklanan cevap gövdesinin üst sınırı (karakter)
MAX_STORED_BODY = 50_000


def run_status(result: SendResult, results: list[RuleResult]) -> RunStatus:
    if not result.ok:
        return RunStatus.ERROR
    return RunStatus.FAILED if any(not item.passed for item in results) else RunStatus.PASSED


def _masked_result(item: RuleResult, secrets: list[str]) -> dict:
    data = {**asdict(item), "type": item.type.value}
    if data.get("actual") is not None:
        data["actual"] = (
            MASK if is_sensitive_path(item.target) else mask_secrets(data["actual"], secrets)
        )
    return data


def save_run(
    db: Session,
    api: ApiDefinition,
    result: SendResult,
    results: list[RuleResult],
    user_id: int | None,
    collection_run_id: int | None = None,
    secret_values: list[str] | None = None,
) -> ApiTestRun:
    secrets = secret_values or []
    response = None
    if result.ok:
        response = {
            "status_code": result.status_code,
            "headers": mask_headers(result.headers, secrets),
            "body": mask_text(result.body, secrets)[:MAX_STORED_BODY],
            "truncated": result.truncated or len(result.body) > MAX_STORED_BODY,
            "size_bytes": result.size_bytes,
        }

    run = ApiTestRun(
        api_definition_id=api.id,
        api_name=api.name,
        method=api.method.value,
        environment_name=result.environment,
        triggered_by_id=user_id,
        collection_run_id=collection_run_id,
        status=run_status(result, results),
        status_code=result.status_code,
        elapsed_ms=result.elapsed_ms,
        passed_count=sum(1 for item in results if item.passed),
        failed_count=sum(1 for item in results if not item.passed),
        error=mask_secrets(result.error, secrets) if result.error else None,
        request=result.request.model_dump(),
        response=response,
        assertion_results=[_masked_result(item, secrets) for item in results],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _summary_fields(run: ApiTestRun) -> dict:
    return {
        "id": run.id,
        "api_definition_id": run.api_definition_id,
        "api_name": run.api_name,
        "method": run.method,
        "environment_name": run.environment_name,
        "status": run.status,
        "status_code": run.status_code,
        "elapsed_ms": run.elapsed_ms,
        "passed_count": run.passed_count,
        "failed_count": run.failed_count,
        "error": run.error,
        "triggered_by_id": run.triggered_by_id,
        "collection_run_id": run.collection_run_id,
        "created_at": run.created_at,
    }


def run_to_summary(run: ApiTestRun) -> TestRunSummary:
    return TestRunSummary(**_summary_fields(run))


def run_to_read(run: ApiTestRun) -> TestRunRead:
    return TestRunRead(
        **_summary_fields(run),
        request=run.request or {},
        response=run.response,
        assertion_results=run.assertion_results or [],
    )
