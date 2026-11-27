"""Giren adaptör: giriş, token yenileme ve "ben kimim" endpoint'leri.

Burada sadece HTTP işi yapılır (gövdeyi oku, use case'i çağır, cevabı biçimle).
Kurallar use case'lerdedir; hatalar errors.py ile HTTP koduna çevrilir.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.adapters.inbound.http.dependencies import CurrentUser, Hasher, Tokens, Users
from app.adapters.inbound.http.schemas.auth import LoginRequest, RefreshRequest
from app.adapters.inbound.http.schemas.auth import TokenPair as TokenPairSchema
from app.adapters.inbound.http.schemas.user import UserRead
from app.adapters.outbound.security.login_limiter import login_limiter
from app.application.ports.auth import TokenPair
from app.application.use_cases.auth import INVALID_CREDENTIALS, Login, RefreshTokens
from app.domain.users import User

router = APIRouter(prefix="/auth", tags=["Kimlik Doğrulama"])


def get_login(users: Users, hasher: Hasher, tokens: Tokens) -> Login:
    return Login(users, hasher, tokens, login_limiter)


def get_refresh_tokens(users: Users, tokens: Tokens) -> RefreshTokens:
    return RefreshTokens(users, tokens)


def _to_schema(pair: TokenPair) -> TokenPairSchema:
    return TokenPairSchema(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post(
    "/login",
    response_model=TokenPairSchema,
    summary="Giriş yap, token al",
    responses={
        401: {"description": INVALID_CREDENTIALS},
        429: {"description": "Çok fazla hatalı deneme; bir süre sonra tekrar deneyin"},
    },
)
def login(
    body: LoginRequest,
    request: Request,
    use_case: Annotated[Login, Depends(get_login)],
) -> TokenPairSchema:
    client = request.client.host if request.client else "?"
    return _to_schema(use_case(body.email, body.password, client))


@router.post(
    "/refresh",
    response_model=TokenPairSchema,
    summary="Refresh token ile yeni token al",
    responses={401: {"description": "Refresh token geçersiz veya süresi dolmuş"}},
)
def refresh(
    body: RefreshRequest,
    use_case: Annotated[RefreshTokens, Depends(get_refresh_tokens)],
) -> TokenPairSchema:
    return _to_schema(use_case(body.refresh_token))


@router.get("/me", response_model=UserRead, summary="Giriş yapmış kullanıcının bilgileri")
def me(user: CurrentUser) -> User:
    return user
