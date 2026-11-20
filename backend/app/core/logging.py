"""Merkezi logging ayarı. Uygulama açılışında bir kez çağrılır."""

import logging
import sys

from app.core.config import settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Gürültülü kütüphaneleri sakinleştir
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
