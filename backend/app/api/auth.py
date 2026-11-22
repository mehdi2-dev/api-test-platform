"""Giriş, token yenileme ve "ben kimim" endpoint'leri."""

import jwt
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
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
    responses={401: {"description": INVALID_CREDENTIALS}},
)
def login(body: LoginRequest, db: DbSession) -> TokenPair:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # Hangi bilginin yanlış olduğunu söylemiyoruz: e-posta tahmin edilmesin
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Hesabınız pasif durumda")
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
