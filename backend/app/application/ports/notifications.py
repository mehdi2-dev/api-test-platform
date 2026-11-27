"""Bildirimlerle ilgili portlar: kanalların saklandığı yer ve mesajı kanala ileten."""

from typing import Protocol

from app.domain.notifications import Notification, NotificationChannel


class NotificationChannelRepository(Protocol):
    def get(self, channel_id: int) -> NotificationChannel | None: ...

    def list_all(self) -> list[NotificationChannel]:
        """Ada göre sıralı."""
        ...

    def enabled(self) -> list[NotificationChannel]: ...

    def save(self, channel: NotificationChannel) -> None: ...

    def delete(self, channel: NotificationChannel) -> None: ...


class NotificationSender(Protocol):
    def deliver(self, channel_type: str, target: str, message: Notification) -> None:
        """Mesajı tek bir kanala iletir (Slack/Teams/webhook: HTTP, email: SMTP).

        Başarısızsa nedenini anlatan bir hata fırlatır.
        """
        ...
