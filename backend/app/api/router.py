"""Tüm endpoint router'larını tek yerde toplar."""

from fastapi import APIRouter

from app.api import apis, auth, collections, environments, health, runs, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["Sistem"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(apis.router)
api_router.include_router(environments.router)
api_router.include_router(runs.router)
api_router.include_router(collections.router)
