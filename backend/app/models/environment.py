"""Ortamlar (Dev, Stage, Prod...) ve ortam değişkenleri (ATOP-27).

Aynı API tanımı farklı ortamlarda çalıştırılabilir: URL'de {{base_url}} yazılır,
hangi ortam seçilirse onun base_url değeri kullanılır.

Gizli (is_secret) değişkenlerin değeri veritabanında şifreli saklanır.
"""

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Environment(TimestampMixin, Base):
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Production ortamında veri değiştiren istekler açık onay olmadan çalışmaz (ATOP-30)
    is_production: Mapped[bool] = mapped_column(Boolean, default=False)

    variables: Mapped[list["EnvironmentVariable"]] = relationship(
        back_populates="environment",
        cascade="all, delete-orphan",
        order_by="EnvironmentVariable.id",
        lazy="selectin",
    )


class EnvironmentVariable(Base):
    __tablename__ = "environment_variables"
    __table_args__ = (UniqueConstraint("environment_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    environment_id: Mapped[int] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(100))
    # is_secret ise şifreli metin, değilse düz değer
    value: Mapped[str] = mapped_column(Text, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)

    environment: Mapped[Environment] = relationship(back_populates="variables")
