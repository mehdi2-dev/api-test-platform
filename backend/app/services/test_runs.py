"""Test çalıştırma sonuçlarının okunması (HTTP şemalarına çevirme).

Kaydın kendisi domain'dedir (app.domain.testing.runs.ApiTestRun.record); save_run,
henüz taşınmamış koleksiyon koşturucu için bir geçiş sarmalayıcısıdır.
"""

from sqlalchemy.orm import Session

from app.adapters.outbound.persistence.test_runs import SqlAlchemyApiTestRunRepository
from app.domain.api_definitions import ApiDefinition
from app.domain.testing.rules import RuleResult
from app.domain.testing.runs import ApiTestRun, SendOutcome, run_status  # noqa: F401
from app.schemas.assertion import TestRunRead, TestRunSummary


def save_run(
    db: Session,
    api: ApiDefinition,
    result: SendOutcome,
    results: list[RuleResult],
    user_id: int | None,
    collection_run_id: int | None = None,
    secret_values: list[str] | None = None,
) -> ApiTestRun:
    run = ApiTestRun.record(
        api=api,
        outcome=result,
        results=results,
        triggered_by_id=user_id,
        collection_run_id=collection_run_id,
        secrets=secret_values,
    )
    SqlAlchemyApiTestRunRepository(db).add(run)
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
