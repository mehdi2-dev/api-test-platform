"""Endpoint'lerin ortak bağımlılıkları: oturum açmış kullanıcı ve rol kontrolü.

Kullanım:
    @router.get("/x")
    def x(user: CurrentUser): ...                      # sadece giriş yapmış olmak yeter

    @router.post("/y", dependencies=[Depends(require_roles(Role.ADMIN, Role.TESTER))])
    def y(): ...                                       # admin veya tester olmalı
"""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import Role, User

bearer_scheme = HTTPBearer(auto_error=False, description="Giriş yapınca aldığınız access token")

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise _unauthorized("Bu işlem için giriş yapmanız gerekiyor")
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except jwt.PyJWTError as exc:
        raise _unauthorized("Token geçersiz veya süresi dolmuş") from exc

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise _unauthorized("Kullanıcı bulunamadı veya pasif")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: Role) -> Callable[[User], User]:
    """Kullanıcının rolü izin verilenler arasında değilse 403 döndürür."""

    def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için yetkiniz yok",
            )
        return user

    return checker
