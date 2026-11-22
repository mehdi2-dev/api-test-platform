"""Kullanıcı yönetimi (sadece Admin)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, require_roles
from app.core.security import hash_password
from app.models.user import Role, User
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(
    prefix="/users",
    tags=["Kullanıcı Yönetimi"],
    responses={
        401: {"description": "Giriş yapılmamış"},
        403: {"description": "Sadece Admin erişebilir"},
    },
)

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]


def _get_or_404(db: DbSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kullanıcı bulunamadı")
    return user


@router.get("", response_model=list[UserRead], summary="Kullanıcıları listele")
def list_users(_: AdminUser, db: DbSession) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kullanıcı ekle",
    responses={409: {"description": "Bu e-posta zaten kayıtlı"}},
)
def create_user(body: UserCreate, _: AdminUser, db: DbSession) -> User:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Bu e-posta zaten kayıtlı")

    user = User(
        email=email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Kullanıcı detayı",
    responses={404: {"description": "Kullanıcı bulunamadı"}},
)
def get_user(user_id: int, _: AdminUser, db: DbSession) -> User:
    return _get_or_404(db, user_id)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Kullanıcıyı güncelle (ad, şifre, rol, aktif/pasif)",
    responses={
        400: {"description": "Admin kendi rolünü düşüremez veya kendini pasifleştiremez"},
        404: {"description": "Kullanıcı bulunamadı"},
    },
)
def update_user(user_id: int, body: UserUpdate, admin: AdminUser, db: DbSession) -> User:
    user = _get_or_404(db, user_id)

    # Sistemde admin kalmaması gibi kazaları önlemek için kendine kısıtlama
    if user.id == admin.id:
        if body.role is not None and body.role != Role.ADMIN:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Kendi rolünüzü düşüremezsiniz")
        if body.is_active is False:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Kendi hesabınızı pasifleştiremezsiniz"
            )

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.password is not None:
        user.hashed_password = hash_password(body.password)
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)
    return user
