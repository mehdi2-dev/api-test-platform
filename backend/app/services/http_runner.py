"""Bir API tanımını gerçek HTTP isteğine çevirip gönderir (ATOP-24, ATOP-26, ATOP-28).

Akış:
1. resolve_spec: tanımdaki {{değişken}}'leri seçilen ortamın değerleriyle doldurur
2. build_request: header, query, body ve kimlik bilgisini ekleyip httpx isteği hazırlar
3. send: isteği gönderir, süreyi ölçer, cevabı döndürür

Test motoru (Epic 5) da istekleri bu modül üzerinden gönderecek; burada sadece
isteği gönderip cevabı ölçüyoruz, doğrulama (assertion) yapmıyoruz.
"""

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.domain.testing.variables import mask_secrets, resolve
from app.models.api_definition import ApiDefinition, AuthType, BodyType
from app.schemas.api_definition import MASK, SendResult, SentRequest

MAX_BODY_CHARS = 200_000
# Bu header'ların değeri sonuçta her zaman maskelenir
SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "x-api-key"}
AUTH_TEXT_FIELDS = ("token", "username", "password", "key_name", "key_value")


@dataclass
class RequestSpec:
    """Değişkenleri çözülmüş, gönderilmeye hazır istek tarifi."""

    method: str
    url: str
    headers: list[tuple[str, str]]
    params: list[tuple[str, str]]
    body_type: BodyType
    body: str | None
    auth_type: AuthType
    auth: dict[str, Any]
    missing: set[str] = field(default_factory=set)


def _enabled_pairs(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(item["key"], item.get("value", "")) for item in items if item.get("enabled", True)]


def resolve_spec(
    api: ApiDefinition, auth: dict[str, Any], variables: dict[str, str]
) -> RequestSpec:
    missing: set[str] = set()

    def r(text: str | None) -> str | None:
        return resolve(text, variables, missing)

    def pairs(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
        return [(r(key), r(value)) for key, value in _enabled_pairs(items)]

    resolved_auth = {
        key: (r(value) if key in AUTH_TEXT_FIELDS else value) for key, value in auth.items()
    }
    body = r(api.body) if api.body_type != BodyType.NONE else None
    return RequestSpec(
        method=api.method.value,
        url=r(api.url).strip(),
        headers=pairs(api.headers or []),
        params=pairs(api.query_params or []),
        body_type=api.body_type,
        body=body,
        auth_type=api.auth_type,
        auth=resolved_auth,
        missing=missing,
    )


def build_request(
    spec: RequestSpec, secret_values: list[str] | None = None
) -> tuple[httpx.Request, SentRequest]:
    """Gönderilecek isteği ve ekranda gösterilecek maskeli özetini hazırlar."""
    secret_values = secret_values or []
    headers = dict(spec.headers)
    params = list(spec.params)
    display_params = list(spec.params)
    secret_header_names = set(SENSITIVE_HEADERS)
    auth = spec.auth

    content: bytes | None = None
    if spec.body_type != BodyType.NONE and spec.body:
        content = spec.body.encode()
        if "content-type" not in {key.lower() for key in headers}:
            headers["Content-Type"] = (
                "application/json" if spec.body_type == BodyType.JSON else "text/plain"
            )

    if spec.auth_type == AuthType.BEARER:
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif spec.auth_type == AuthType.BASIC:
        raw = f"{auth['username']}:{auth['password']}".encode()
        headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"
    elif spec.auth_type == AuthType.API_KEY:
        if auth.get("location") == "query":
            params.append((auth["key_name"], auth["key_value"]))
            display_params.append((auth["key_name"], MASK))
        else:
            headers[auth["key_name"]] = auth["key_value"]
            secret_header_names.add(auth["key_name"].lower())

    request = httpx.Request(
        spec.method, spec.url, headers=headers, params=params or None, content=content
    )
    display_url = str(httpx.Request("GET", spec.url, params=display_params or None).url)
    display_headers = {
        key: (MASK if key.lower() in secret_header_names else mask_secrets(value, secret_values))
        for key, value in headers.items()
    }
    summary = SentRequest(
        method=spec.method,
        url=mask_secrets(display_url, secret_values),
        headers=display_headers,
    )
    return request, summary


def _failed(method: str, url: str, error: str, environment: str | None) -> SendResult:
    """İstek hiç gönderilemediğinde dönen sonuç."""
    return SendResult(
        ok=False,
        elapsed_ms=0,
        error=error,
        request=SentRequest(method=method, url=url, headers={}),
        environment=environment,
    )


def send(
    api: ApiDefinition,
    auth: dict[str, Any],
    transport: httpx.BaseTransport | None = None,
    variables: dict[str, str] | None = None,
    secret_values: list[str] | None = None,
    environment_name: str | None = None,
) -> SendResult:
    """İsteği gönderir. Ağ hatalarında istisna fırlatmaz, sonucu error alanıyla döndürür."""
    secret_values = secret_values or []
    spec = resolve_spec(api, auth, variables or {})
    safe_url = mask_secrets(spec.url, secret_values)

    if spec.missing:
        names = ", ".join(sorted(spec.missing))
        hint = (
            f"'{environment_name}' ortamında bu değişkenler yok."
            if environment_name
            else "Bir ortam seçin."
        )
        return _failed(
            spec.method, safe_url, f"Tanımsız değişken: {names}. {hint}", environment_name
        )

    if not spec.url.startswith(("http://", "https://")):
        return _failed(
            spec.method,
            safe_url,
            f"URL http:// veya https:// ile başlamalı: {safe_url}",
            environment_name,
        )

    try:
        request, summary = build_request(spec, secret_values)
    except (httpx.InvalidURL, httpx.UnsupportedProtocol, ValueError) as exc:
        return _failed(spec.method, safe_url, f"Geçersiz istek: {exc}", environment_name)

    started = time.perf_counter()

    def elapsed() -> float:
        return round((time.perf_counter() - started) * 1000, 1)

    timeout = settings.request_timeout_seconds
    error: str | None = None
    try:
        with httpx.Client(transport=transport, timeout=timeout, follow_redirects=True) as client:
            response = client.send(request)
            raw = response.content
    except httpx.TimeoutException:
        error = f"İstek zaman aşımına uğradı ({timeout:g} sn)"
    except httpx.ConnectError as exc:
        error = f"Sunucuya bağlanılamadı: {exc}"
    except httpx.HTTPError as exc:
        error = f"İstek başarısız: {exc}"

    if error is not None:
        return SendResult(
            ok=False,
            elapsed_ms=elapsed(),
            error=mask_secrets(error, secret_values),
            request=summary,
            environment=environment_name,
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
        environment=environment_name,
    )
