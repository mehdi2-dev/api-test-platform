"""Test çalıştırma kayıtlarını HTTP şemalarına çevirir."""

from app.adapters.inbound.http.schemas.assertion import TestRunRead, TestRunSummary
from app.domain.testing.runs import ApiTestRun


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
