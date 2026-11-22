"""Merkezi logging ayarı. Uygulama açılışında bir kez çağrılır."""

import logging
import re
import sys

from app.core.config import settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Log satırlarında token/şifre görünmesin (ATOP-50)
_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1********"),
    (re.compile(r"(?i)(basic\s+)[A-Za-z0-9+/=]+"), r"\1********"),
    (
        re.compile(
            r"(?i)((?:password|passwd|token|api[-_]?key|secret)[\"']?\s*[:=]\s*[\"']?)"
            r"[^\"'&\s,}]+"
        ),
        r"\1********",
    ),
]


def mask_log_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Mesajı biçimlendirip içindeki hassas değerleri maskeler."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = mask_log_text(message)
        if masked != message:
            record.msg, record.args = masked, None
        return True


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(SensitiveDataFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # Gürültülü kütüphaneleri sakinleştir
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
