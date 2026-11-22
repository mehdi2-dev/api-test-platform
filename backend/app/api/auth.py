"""Giriş, token yenileme ve "ben kimim" endpoint'leri."""

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.rate_limit import login_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenPair
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["Kimlik Doğrulama"])

INVALID_CREDENTIALS = "E-posta veya şifre hatalı"


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Giriş yap, token al",
    responses={
        401: {"description": INVALID_CREDENTIALS},
        429: {"description": "Çok fazla hatalı deneme; bir süre sonra tekrar deneyin"},
    },
)
def login(body: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    email = body.email.lower()
    # Kaba kuvvet (brute-force) koruması: aynı e-posta + IP için hatalı deneme sınırı
    client = request.client.host if request.client else "?"
    key = f"{client}|{email}"
    wait = login_limiter.retry_after(key)
    if wait:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Çok fazla hatalı deneme. Yaklaşık {minutes} dakika sonra tekrar deneyin.",
            headers={"Retry-After": str(wait)},
        )

    user = db.scalar(select(User).where(User.email == email))
    # Hangi bilginin yanlış olduğunu söylemiyoruz: e-posta tahmin edilmesin
    if user is None or not verify_password(body.password, user.hashed_password):
        login_limiter.failed(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Hesabınız pasif durumda")
    login_limiter.succeeded(key)
    return _token_pair(user)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Refresh token ile yeni token al",
    responses={401: {"description": "Refresh token geçersiz veya süresi dolmuş"}},
)
def refresh(body: RefreshRequest, db: DbSession) -> TokenPair:
    try:
        payload = decode_token(body.refresh_token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Refresh token geçersiz veya süresi dolmuş"
        ) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Kullanıcı bulunamadı veya pasif")
    return _token_pair(user)


@router.get("/me", response_model=UserRead, summary="Giriş yapmış kullanıcının bilgileri")
def me(user: CurrentUser) -> User:
    return user
