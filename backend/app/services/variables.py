"""Değişken çözümleme motoru (ATOP-28).

Metindeki {{ad}} yer tutucularını ortamdaki değerlerle değiştirir:

    resolve("{{base_url}}/users", {"base_url": "https://dev.ornek.com"}, missing)
    -> "https://dev.ornek.com/users"

Tanımsız değişkenler olduğu gibi bırakılır ve `missing` kümesine eklenir; böylece
çağıran taraf "şu değişkenler eksik" diyebilir.
"""

import re
from urllib.parse import quote

from app.schemas.api_definition import MASK

VARIABLE_NAME = r"[A-Za-z_][A-Za-z0-9_.-]*"
PLACEHOLDER = re.compile(r"\{\{\s*(" + VARIABLE_NAME + r")\s*\}\}")


def find_variables(text: str | None) -> set[str]:
    """Metinde geçen değişken adları."""
    return set(PLACEHOLDER.findall(text or ""))


def resolve(text: str | None, variables: dict[str, str], missing: set[str]) -> str | None:
    if not text:
        return text

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
