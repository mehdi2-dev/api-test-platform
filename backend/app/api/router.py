"""Tüm endpoint router'larını tek yerde toplar."""

from fastapi import APIRouter

from app.api import auth, health, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["Sistem"])
api_router.include_router(auth.router)
api_router.include_router(users.router)
