"""Değişken çözümleme motoru (ATOP-28).

Metindeki {{ad}} yer tutucularını ortamdaki değerlerle değiştirir:

    resolve("{{base_url}}/users", {"base_url": "https://dev.ornek.com"}, missing)
    -> "https://dev.ornek.com/users"

Tanımsız değişkenler olduğu gibi bırakılır ve `missing` kümesine eklenir; böylece
çağıran taraf "şu değişkenler eksik" diyebilir.

Hazır (dinamik) değişkenler: her kullanıldığı yerde yeni değer üretir; ortamda tanımlamaya
gerek yoktur. Her çalıştırmada farklı veri gereken testler için (ör. benzersiz e-posta):

    {{$uuid}}          3f2b...-...   benzersiz kimlik
    {{$timestamp}}     1763830000    Unix zamanı (saniye)
    {{$isoTimestamp}}  2026-11-22T19:30:00+00:00
    {{$randomInt}}     0-99999 arası sayı
"""

import random
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import quote

from app.schemas.api_definition import MASK

VARIABLE_NAME = r"[A-Za-z_][A-Za-z0-9_.-]*"
PLACEHOLDER = re.compile(r"\{\{\s*(" + VARIABLE_NAME + r")\s*\}\}")

DYNAMIC: dict[str, Callable[[], str]] = {
    "uuid": lambda: str(uuid.uuid4()),
    "timestamp": lambda: str(int(datetime.now(UTC).timestamp())),
    "isoTimestamp": lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    "randomInt": lambda: str(random.randint(0, 99_999)),
}
DYNAMIC_PLACEHOLDER = re.compile(r"\{\{\s*\$(" + "|".join(DYNAMIC) + r")\s*\}\}")


def find_variables(text: str | None) -> set[str]:
    """Metinde geçen değişken adları."""
    return set(PLACEHOLDER.findall(text or ""))


def resolve(text: str | None, variables: dict[str, str], missing: set[str]) -> str | None:
    if not text:
        return text
    text = DYNAMIC_PLACEHOLDER.sub(lambda match: DYNAMIC[match.group(1)](), text)

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in variables:
            return variables[name]
        missing.add(name)
        return match.group(0)

    return PLACEHOLDER.sub(replace, text)


def mask_secrets(text: str, secret_values: list[str]) -> str:
    """Gizli değişken değerlerini (ve URL'de kodlanmış hallerini) MASK ile değiştirir."""
    for value in sorted(secret_values, key=len, reverse=True):
        if not value:
            continue
        text = text.replace(value, MASK)
        encoded = quote(value, safe="")
        if encoded != value:
            text = text.replace(encoded, MASK)
    return text
