"""Kullanıcı ve roller.

Roller:
- admin:  her şeyi yapar, kullanıcıları yönetir
- tester: API tanımlar, test oluşturur ve çalıştırır
- viewer: sadece görüntüler

Saf Python sınıfıdır. Veritabanı tablosuyla eşlemesi
app.adapters.outbound.persistence.users içindedir; burada ORM bilgisi yoktur.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.errors import ValidationFailed


class Role(StrEnum):
    ADMIN = "admin"
    TESTER = "tester"
    VIEWER = "viewer"


@dataclass(eq=False, kw_only=True)
class User:
    email: str
    full_name: str
    # Şifrenin kendisi asla saklanmaz, sadece özeti (hash)
    hashed_password: str = field(repr=False)
    role: Role = Role.VIEWER
    is_active: bool = True
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @staticmethod
    def normalize_email(email: str) -> str:
        """E-posta adresleri büyük/küçük harf duyarsızdır."""
        return email.lower()

    def is_same_as(self, other: "User") -> bool:
        return self is other or (self.id is not None and self.id == other.id)

    def has_role(self, *roles: Role) -> bool:
        return self.role in roles

    def update(
        self,
        *,
        changed_by: "User",
        full_name: str | None = None,
        hashed_password: str | None = None,
        role: Role | None = None,
        is_active: bool | None = None,
    ) -> None:
        """Sadece verilen alanları değiştirir.

        Sistemde admin kalmaması gibi kazaları önlemek için kişi kendi rolünü
        düşüremez ve kendi hesabını pasifleştiremez.
        """
        if self.is_same_as(changed_by):
            if role is not None and role != Role.ADMIN:
                raise ValidationFailed("Kendi rolünüzü düşüremezsiniz")
            if is_active is False:
                raise ValidationFailed("Kendi hesabınızı pasifleştiremezsiniz")

        if full_name is not None:
            self.full_name = full_name
        if hashed_password is not None:
            self.hashed_password = hashed_password
        if role is not None:
            self.role = role
        if is_active is not None:
            self.is_active = is_active
