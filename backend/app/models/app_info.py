"""Migration altyapısını doğrulamak için küçük bir anahtar/değer tablosu.

Uygulama sürümü gibi sistem bilgilerini tutar. Gerçek modeller (User, ApiDefinition ...)
sonraki task'larda eklenecek.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AppInfo(TimestampMixin, Base):
    __tablename__ = "app_info"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))
