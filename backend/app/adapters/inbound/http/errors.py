"""Domain/use case hatalarını HTTP cevabına çevirir.

Domain "bulunamadı", "çakışma var" der; 404 veya 409'u bilmez. Çeviri burada, kenarda yapılır.
Cevap biçimi FastAPI'nin HTTPException'ı ile aynıdır: {"detail": "..."}.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.application.errors import AuthenticationFailed, TooManyAttempts
from app.domain.errors import (
    AccessDenied,
    Conflict,
    DomainError,
    InvalidInput,
    NotFound,
    SecretUnreadable,
)

STATUS_CODES: list[tuple[type[DomainError], int]] = [
    (NotFound, status.HTTP_404_NOT_FOUND),
    (AccessDenied, status.HTTP_403_FORBIDDEN),
    (Conflict, status.HTTP_409_CONFLICT),
    (AuthenticationFailed, status.HTTP_401_UNAUTHORIZED),
    (TooManyAttempts, status.HTTP_429_TOO_MANY_REQUESTS),
    (InvalidInput, 422),
    (SecretUnreadable, status.HTTP_500_INTERNAL_SERVER_ERROR),
]


def status_code_for(error: DomainError) -> int:
    for error_type, code in STATUS_CODES:
        if isinstance(error, error_type):
            return code
    return status.HTTP_400_BAD_REQUEST  # ValidationFailed ve diğer kural ihlalleri


async def domain_error_handler(_: Request, error: DomainError) -> JSONResponse:
    headers = None
    if isinstance(error, TooManyAttempts):
        headers = {"Retry-After": str(error.retry_after)}
    return JSONResponse(
        status_code=status_code_for(error),
        content={"detail": error.message},
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
