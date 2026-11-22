"""Kullanıcı modeli ve roller.

Roller (proje tanımındaki gibi):
- admin:  her şeyi yapar, kullanıcıları yönetir
- tester: API tanımlar, test oluşturur ve çalıştırır
- viewer: sadece görüntüler
"""

from enum import StrEnum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Role(StrEnum):
    ADMIN = "admin"
    TESTER = "tester"
    VIEWER = "viewer"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    # Şifrenin kendisi asla saklanmaz, sadece bcrypt özeti (hash)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda roles: [r.value for r in roles]),
        default=Role.VIEWER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
