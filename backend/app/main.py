"""FastAPI uygulamasının giriş noktası.

Çalıştırma:  uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("%s başlatıldı (ortam: %s)", settings.app_name, settings.environment)
    yield
    logger.info("%s kapatılıyor", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Kod yazmadan API testi tanımlama ve çalıştırma platformu.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} çalışıyor", "docs": "/docs"}
