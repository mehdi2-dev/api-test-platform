"""Bir API tanımını gerçek HTTP isteğine çevirip gönderir (ATOP-24, ATOP-26).

Test motoru (Epic 5) da istekleri bu modül üzerinden gönderecek; burada sadece
isteği gönderip cevabı ölçüyoruz, doğrulama (assertion) yapmıyoruz.
"""

import base64
import json
import time
from typing import Any

import httpx

from app.core.config import settings
from app.models.api_definition import ApiDefinition, AuthType, BodyType
from app.schemas.api_definition import MASK, SendResult, SentRequest

MAX_BODY_CHARS = 200_000
# Bu header'ların değeri sonuçta her zaman maskelenir
SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "x-api-key"}


def _enabled_pairs(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(item["key"], item.get("value", "")) for item in items if item.get("enabled", True)]


def build_request(api: ApiDefinition, auth: dict[str, Any]) -> tuple[httpx.Request, SentRequest]:
    """Gönderilecek isteği ve ekranda gösterilecek maskeli özetini hazırlar."""
    headers = dict(_enabled_pairs(api.headers or []))
    params = _enabled_pairs(api.query_params or [])
    display_params = list(params)
    secret_header_names = set(SENSITIVE_HEADERS)

    content: bytes | None = None
    if api.body_type != BodyType.NONE and api.body:
        content = api.body.encode()
        lower_keys = {key.lower() for key in headers}
        if "content-type" not in lower_keys:
            headers["Content-Type"] = (
                "application/json" if api.body_type == BodyType.JSON else "text/plain"
            )

    if api.auth_type == AuthType.BEARER:
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif api.auth_type == AuthType.BASIC:
        raw = f"{auth['username']}:{auth['password']}".encode()
        headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"
    elif api.auth_type == AuthType.API_KEY:
        if auth.get("location") == "query":
            params.append((auth["key_name"], auth["key_value"]))
            display_params.append((auth["key_name"], MASK))
        else:
            headers[auth["key_name"]] = auth["key_value"]
            secret_header_names.add(auth["key_name"].lower())

    request = httpx.Request(
        api.method.value, api.url, headers=headers, params=params or None, content=content
    )
    display_url = str(httpx.Request("GET", api.url, params=display_params or None).url)
    display_headers = {
        key: (MASK if key.lower() in secret_header_names else value)
        for key, value in headers.items()
    }
    return request, SentRequest(method=api.method.value, url=display_url, headers=display_headers)


def send(
    api: ApiDefinition,
    auth: dict[str, Any],
    transport: httpx.BaseTransport | None = None,
) -> SendResult:
    """İsteği gönderir. Ağ hatalarında istisna fırlatmaz, sonucu error alanıyla döndürür."""
    started = time.perf_counter()

    def elapsed() -> float:
        return round((time.perf_counter() - started) * 1000, 1)

    if "{{" in api.url:
        return SendResult(
            ok=False,
            elapsed_ms=0,
            error="URL'de çözülmemiş değişken var ({{...}}). Ortamlar eklenince çalışacak.",
            request=SentRequest(method=api.method.value, url=api.url, headers={}),
        )

    try:
        request, summary = build_request(api, auth)
    except (httpx.InvalidURL, httpx.UnsupportedProtocol, ValueError) as exc:
        return SendResult(
            ok=False,
            elapsed_ms=0,
            error=f"Geçersiz istek: {exc}",
            request=SentRequest(method=api.method.value, url=api.url, headers={}),
        )

    timeout = settings.request_timeout_seconds
    try:
        with httpx.Client(transport=transport, timeout=timeout, follow_redirects=True) as client:
            response = client.send(request)
            raw = response.content
    except httpx.TimeoutException:
        return SendResult(
            ok=False,
            elapsed_ms=elapsed(),
            error=f"İstek zaman aşımına uğradı ({timeout:g} sn)",
            request=summary,
        )
    except httpx.ConnectError as exc:
        return SendResult(
            ok=False,
            elapsed_ms=elapsed(),
            error=f"Sunucuya bağlanılamadı: {exc}",
            request=summary,
        )
    except httpx.HTTPError as exc:
        return SendResult(
            ok=False, elapsed_ms=elapsed(), error=f"İstek başarısız: {exc}", request=summary
        )

    text = response.text
    body_json: Any | None = None
    try:
        body_json = json.loads(text) if text.strip() else None
    except ValueError:
        body_json = None

    return SendResult(
        ok=True,
        status_code=response.status_code,
        elapsed_ms=elapsed(),
        size_bytes=len(raw),
        headers=dict(response.headers),
        body=text[:MAX_BODY_CHARS],
        body_json=body_json,
        truncated=len(text) > MAX_BODY_CHARS,
        request=summary,
    )
