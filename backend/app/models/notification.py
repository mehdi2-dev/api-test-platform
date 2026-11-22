"""Bildirim kanalları (ATOP-48).

Bir koleksiyon çalıştırması bittiğinde (elle, arka planda ya da zamanlanmış) etkin
kanallara mesaj gönderilir. Varsayılan: sadece başarısız olduğunda.

Kanal tipleri:
    slack    -> Slack "Incoming Webhook" adresi
    teams    -> Microsoft Teams "Incoming Webhook" adresi
    webhook  -> herhangi bir adres; JSON olarak tüm sonuç gönderilir
    email    -> e-posta adres(ler)i (virgülle); SMTP ayarları .env'de

Webhook adresleri gizli sayılır (adresi bilen kanala mesaj atabilir): şifreli saklanır.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NotificationChannel(TimestampMixin, Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    target_encrypted: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # "failure": sadece kalan/hatalı çalıştırmalarda, "always": her çalıştırmada
    notify_on: Mapped[str] = mapped_column(String(20), default="failure")

    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
