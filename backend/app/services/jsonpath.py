"""Basit JSONPath (ATOP-34).

Desteklenen yazımlar:
    $                     -> cevabın tamamı
    $.status              -> {"status": ...}
    $.data.items[0].id    -> iç içe alan ve dizi elemanı
    $.items[-1]           -> dizinin son elemanı
    $['alan adı']         -> boşluk/özel karakter içeren alan
    data.name             -> başta $ yazmak zorunlu değil

Joker (*) ve filtre ifadeleri bilerek desteklenmiyor: her yol tek bir değere işaret eder,
böylece "eşittir" gibi kontrollerin anlamı nettir.
"""

import re
from typing import Any

_TOKEN = re.compile(
    r"\.(?P<key>[A-Za-z_][\w-]*)"  # .alan
    r"|\[(?P<index>-?\d+)\]"  # [0]
    r"|\[(?P<quote>['\"])(?P<qkey>.*?)(?P=quote)\]"  # ['alan adı']
)

# Yolun gösterdiği alan yoksa dönen işaret (None'dan ayırmak için: alan var ve değeri null)
MISSING = object()

Token = tuple[str, str | int]


def parse(path: str) -> list[Token]:
    """'$.data[0].id' -> [('key', 'data'), ('index', 0), ('key', 'id')]"""
    text = path.strip()
    if not text:
        raise ValueError("JSONPath boş olamaz")
    if text.startswith("$"):
        text = text[1:]
    elif not text.startswith((".", "[")):
        text = "." + text

    tokens: list[Token] = []
    position = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None:
            raise ValueError(f"Geçersiz JSONPath: '{path}' ({position + 1}. karakter civarı)")
        if match.group("key") is not None:
            tokens.append(("key", match.group("key")))
        elif match.group("index") is not None:
            tokens.append(("index", int(match.group("index"))))
        else:
            tokens.append(("key", match.group("qkey")))
        position = match.end()
    return tokens


def extract(data: Any, path: str) -> Any:
    """Yolun gösterdiği değeri döndürür; yoksa MISSING."""
    current = data
    for kind, value in parse(path):
        if kind == "key":
            if not isinstance(current, dict) or value not in current:
                return MISSING
            current = current[value]
        else:
            if not isinstance(current, list) or not -len(current) <= value < len(current):
                return MISSING
            current = current[value]
    return current
