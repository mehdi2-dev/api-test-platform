"""Uygulama ilk açıldığında gereken başlangıç verileri."""

import logging

from sqlalchemy.orm import Session

from app.adapters.outbound.persistence.users import SqlAlchemyUserRepository
from app.adapters.outbound.security.passwords import BcryptPasswordHasher
from app.application.use_cases.users import EnsureFirstAdmin
from app.core.config import settings
from app.domain.users import User

logger = logging.getLogger(__name__)


def ensure_first_admin(db: Session) -> User | None:
    """Veritabanında hiç kullanıcı yoksa .env'deki bilgilerle ilk admini oluşturur."""
    admin = EnsureFirstAdmin(SqlAlchemyUserRepository(db), BcryptPasswordHasher())(
        email=settings.first_admin_email,
        full_name=settings.first_admin_name,
        password=settings.first_admin_password,
    )
    if admin is not None:
        logger.warning(
            "İlk admin oluşturuldu: %s — giriş yaptıktan sonra şifresini değiştirin", admin.email
        )
    return admin
