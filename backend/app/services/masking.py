"""Hassas verilerin raporlarda ve loglarda maskelenmesi (ATOP-50).

İki katman var:
1. Bilinen gizli değerler: ortamın gizli değişkenleri, cevaptan "gizli" olarak alınan
   değerler. Metnin neresinde geçerse geçsin ******** olur (variables.mask_secrets).
2. Hassas alan adları: JSON cevaplardaki token, password, api_key, secret... alanlarının
   değeri ve Authorization / Cookie gibi header'lar. Bunlar değerini bilmesek de maskelenir.

Maskeleme sadece SAKLANAN ve GÖSTERİLEN veriye uygulanır. Kurallar (assertion) ve
değişken çıkarma, maskelenmemiş gerçek cevap üzerinde çalışır; yani $.access_token'ı
cevaptan almak yine mümkündür.
"""

import json
import re
from typing import Any

from app.schemas.api_definition import MASK
from app.services.variables import mask_secrets

SENSITIVE_KEY = re.compile(
    r"(pass(word|wd)?|secret|token|api[-_]?key|authorization|credential|private[-_]?key|session)",
    re.IGNORECASE,
)
SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
}


def _mask_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, dict | list):
        return _walk(value)
    return MASK


def _walk(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: (_mask_value(value) if SENSITIVE_KEY.search(str(key)) else _walk(value))
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_walk(item) for item in data]
    return data


def mask_json_text(text: str) -> str:
    """JSON ise hassas alanların değerini maskeler; değişiklik yoksa metni aynen bırakır."""
    if not text or not text.strip():
        return text
    try:
        data = json.loads(text)
    except ValueError:
        return text
    masked = _walk(data)
    if masked == data:
        return text
    return json.dumps(masked, ensure_ascii=False)


def mask_headers(headers: dict[str, str], secret_values: list[str] | None = None) -> dict[str, str]:
    return {
        key: (
            MASK if key.lower() in SENSITIVE_HEADERS else mask_secrets(value, secret_values or [])
        )
        for key, value in headers.items()
    }


def is_sensitive_path(path: str | None) -> bool:
    """$.data.access_token gibi bir JSONPath hassas bir alana mı işaret ediyor?"""
    if not path:
        return False
    last = re.split(r"[.\[\]'\"]+", path.strip())
    names = [part for part in last if part and part != "$" and not part.lstrip("-").isdigit()]
    return bool(names) and bool(SENSITIVE_KEY.search(names[-1]))


def mask_text(text: str, secret_values: list[str] | None = None) -> str:
    """Hem bilinen gizli değerleri hem de JSON'daki hassas alanları maskeler."""
    return mask_json_text(mask_secrets(text, secret_values or []))
