"""FastAPI uygulamasının giriş noktası.

Çalıştırma:  uvicorn app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.inbound.http.errors import register_error_handlers
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.init_db import ensure_first_admin
from app.db.session import SessionLocal

setup_logging()
logger = logging.getLogger(__name__)


def _bootstrap_data() -> None:
    """İlk admin gibi başlangıç verilerini oluşturur.

    Veritabanı hazır değilse hatayı loglar ama uygulamayı durdurmaz.
    """
    try:
        with SessionLocal() as db:
            ensure_first_admin(db)
    except Exception:
        logger.exception("Başlangıç verileri oluşturulamadı (migration'lar uygulandı mı?)")


def check_security_settings() -> None:
    """Güvensiz ayarlarla prod'da açılmayı engeller; geliştirmede sadece uyarır (ATOP-49)."""
    warnings = settings.security_warnings()
    if settings.environment == "production" and warnings:
        raise RuntimeError("Güvensiz ayarlarla production başlatılamaz: " + "; ".join(warnings))
    for warning in warnings:
        logger.warning("Güvenlik uyarısı: %s", warning)


@asynccontextmanager
async def lifespan(_: FastAPI):
    check_security_settings()
    _bootstrap_data()
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Tarayıcıya yönelik temel güvenlik başlıkları."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith(settings.api_prefix):
        # API cevapları (token, test sonuçları) tarayıcı önbelleğinde kalmasın
        response.headers.setdefault("Cache-Control", "no-store")
    return response


register_error_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} çalışıyor", "docs": "/docs"}
