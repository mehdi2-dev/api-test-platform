"""Giren adaptör: kullanıcı yönetimi (sadece Admin)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.adapters.inbound.http.dependencies import Hasher, Users, require_roles
from app.application.use_cases.users import CreateUser, GetUser, ListUsers, UpdateUser
from app.domain.users import Role, User
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


def get_list_users(users: Users) -> ListUsers:
    return ListUsers(users)


def get_get_user(users: Users) -> GetUser:
    return GetUser(users)


def get_create_user(users: Users, hasher: Hasher) -> CreateUser:
    return CreateUser(users, hasher)


def get_update_user(users: Users, hasher: Hasher) -> UpdateUser:
    return UpdateUser(users, hasher)


@router.get("", response_model=list[UserRead], summary="Kullanıcıları listele")
def list_users(
    _: AdminUser,
    use_case: Annotated[ListUsers, Depends(get_list_users)],
) -> list[User]:
    return use_case()


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kullanıcı ekle",
    responses={409: {"description": "Bu e-posta zaten kayıtlı"}},
)
def create_user(
    body: UserCreate,
    _: AdminUser,
    use_case: Annotated[CreateUser, Depends(get_create_user)],
) -> User:
    return use_case(
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role=body.role,
    )


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Kullanıcı detayı",
    responses={404: {"description": "Kullanıcı bulunamadı"}},
)
def get_user(
    user_id: int,
    _: AdminUser,
    use_case: Annotated[GetUser, Depends(get_get_user)],
) -> User:
    return use_case(user_id)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Kullanıcıyı güncelle (ad, şifre, rol, aktif/pasif)",
    responses={
        400: {"description": "Admin kendi rolünü düşüremez veya kendini pasifleştiremez"},
        404: {"description": "Kullanıcı bulunamadı"},
    },
)
def update_user(
    user_id: int,
    body: UserUpdate,
    admin: AdminUser,
    use_case: Annotated[UpdateUser, Depends(get_update_user)],
) -> User:
    return use_case(
        admin,
        user_id,
        full_name=body.full_name,
        password=body.password,
        role=body.role,
        is_active=body.is_active,
    )
