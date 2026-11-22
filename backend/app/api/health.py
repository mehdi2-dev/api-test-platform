"""Sağlık kontrolü: uygulama, veritabanı ve Redis ayakta mı?"""

import logging
from typing import Literal

import redis
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

logger = logging.getLogger(__name__)
router = APIRouter()

CheckStatus = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: CheckStatus
    app: str
    environment: str
    checks: dict[str, CheckStatus]


def check_database() -> CheckStatus:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        logger.exception("Veritabanı sağlık kontrolü başarısız")
        return "error"


def check_redis() -> CheckStatus:
    try:
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        return "ok"
    except Exception:
        logger.exception("Redis sağlık kontrolü başarısız")
        return "error"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Sağlık kontrolü",
    responses={
        503: {
            "model": HealthResponse,
            "description": "Veritabanı veya Redis'e ulaşılamıyor",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "app": "API Test Otomasyon Platformu",
                        "environment": "development",
                        "checks": {"database": "ok", "redis": "error"},
                    },
                },
            },
        },
    },
)
def health(response: Response) -> HealthResponse:
    checks = {"database": check_database(), "redis": check_redis()}
    overall: CheckStatus = "ok" if all(v == "ok" for v in checks.values()) else "error"
    if overall == "error":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status=overall,
        app=settings.app_name,
        environment=settings.environment,
        checks=checks,
    )


@router.get("/ping", summary="Basit canlılık kontrolü (bağımlılık kontrol etmez)")
def ping() -> dict[str, str]:
    return {"ping": "pong"}
