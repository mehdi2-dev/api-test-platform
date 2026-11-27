"""Bildirim kanalı tablosu, domain eşlemesi ve repository'nin SQLAlchemy adaptörü.

Tablo şeması eski modelle birebir aynıdır; migration gerekmez.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Table, Text, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.notifications import NotificationChannel

notification_channels_table = Table(
    "notification_channels",
    Base.metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("type", String(20), nullable=False),
    Column("target_encrypted", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("notify_on", String(20), nullable=False, default="failure"),
    Column("last_sent_at", DateTime(timezone=True), nullable=True),
    Column("last_status", String(20), nullable=True),
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    ),
)

Base.registry.map_imperatively(NotificationChannel, notification_channels_table)


class SqlAlchemyNotificationChannelRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, channel_id: int) -> NotificationChannel | None:
        return self._session.get(NotificationChannel, channel_id)

    def list_all(self) -> list[NotificationChannel]:
        query = select(NotificationChannel).order_by(notification_channels_table.c.name)
        return list(self._session.scalars(query))

    def enabled(self) -> list[NotificationChannel]:
        query = select(NotificationChannel).where(notification_channels_table.c.enabled.is_(True))
        return list(self._session.scalars(query))

    def save(self, channel: NotificationChannel) -> None:
        self._session.add(channel)
        self._session.commit()
        self._session.refresh(channel)

    def delete(self, channel: NotificationChannel) -> None:
        self._session.delete(channel)
        self._session.commit()
