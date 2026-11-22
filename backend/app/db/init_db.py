"""Uygulama ilk açıldığında gereken başlangıç verileri."""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import Role, User

logger = logging.getLogger(__name__)


def ensure_first_admin(db: Session) -> User | None:
    """Veritabanında hiç kullanıcı yoksa .env'deki bilgilerle ilk admini oluşturur."""
    user_count = db.scalar(select(func.count()).select_from(User))
    if user_count:
        return None

    admin = User(
        email=settings.first_admin_email.lower(),
        full_name=settings.first_admin_name,
        hashed_password=hash_password(settings.first_admin_password),
        role=Role.ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    logger.warning(
        "İlk admin oluşturuldu: %s — giriş yaptıktan sonra şifresini değiştirin", admin.email
    )
    return admin
