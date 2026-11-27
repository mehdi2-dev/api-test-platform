"""Tüm endpoint router'larını tek yerde toplar."""

from fastapi import APIRouter

from app.adapters.inbound.http import (
    apis,
    auth,
    collections,
    dashboard,
    environments,
    notifications,
    runs,
    schedules,
    users,
)
from app.api import health

api_router = APIRouter()
api_router.include_router(health.router, tags=["Sistem"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(apis.router)
api_router.include_router(environments.router)
api_router.include_router(runs.router)
api_router.include_router(collections.router)
api_router.include_router(schedules.router)
api_router.include_router(dashboard.router)
api_router.include_router(notifications.router)
