"""Use case'ler: bildirim kanalı yönetimi ve biten çalıştırmalar için bildirim gönderme.

Bir kanal hata verirse diğerleri yine denenir ve hata kanalın kendisine yazılır
(last_status / last_error); böylece bildirim sorunu testin sonucunu asla bozmaz.
"""

import logging
from dataclasses import dataclass

from app.application.ports.notifications import NotificationChannelRepository, NotificationSender
from app.application.ports.schedules import Clock
from app.application.ports.security import Cipher
from app.application.ports.testing import ApiTestRunRepository
from app.domain.collections import CollectionRun
from app.domain.errors import NotFound
from app.domain.notifications import (
    Notification,
    NotificationChannel,
    build_notification,
    check_target,
    sample_notification,
)

logger = logging.getLogger(__name__)


class ListChannels:
    def __init__(self, channels: NotificationChannelRepository) -> None:
        self._channels = channels

    def __call__(self) -> list[NotificationChannel]:
        return self._channels.list_all()


class GetChannel:
    def __init__(self, channels: NotificationChannelRepository) -> None:
        self._channels = channels

    def __call__(self, channel_id: int) -> NotificationChannel:
        channel = self._channels.get(channel_id)
        if channel is None:
            raise NotFound("Kanal bulunamadı")
        return channel


class CreateChannel:
    def __init__(self, channels: NotificationChannelRepository, cipher: Cipher) -> None:
        self._channels = channels
        self._cipher = cipher

    def __call__(
        self, *, name: str, channel_type: str, target: str, enabled: bool, notify_on: str
    ) -> NotificationChannel:
        channel = NotificationChannel(
            name=name.strip(),
            type=channel_type,
            target_encrypted=self._cipher.encrypt(check_target(channel_type, target)),
            enabled=enabled,
            notify_on=notify_on,
        )
        self._channels.save(channel)
        return channel


class UpdateChannel:
    """Sadece verilen alanlar değişir; target verilmezse kayıtlı adres korunur."""

    def __init__(self, channels: NotificationChannelRepository, cipher: Cipher) -> None:
        self._channels = channels
        self._cipher = cipher

    def __call__(
        self,
        channel_id: int,
        *,
        name: str | None = None,
        target: str | None = None,
        enabled: bool | None = None,
        notify_on: str | None = None,
    ) -> NotificationChannel:
        channel = GetChannel(self._channels)(channel_id)
        if name is not None:
            channel.name = name.strip()
        if target is not None:
            channel.target_encrypted = self._cipher.encrypt(check_target(channel.type, target))
        if enabled is not None:
            channel.enabled = enabled
        if notify_on is not None:
            channel.notify_on = notify_on
        self._channels.save(channel)
        return channel


class DeleteChannel:
    def __init__(self, channels: NotificationChannelRepository) -> None:
        self._channels = channels

    def __call__(self, channel_id: int) -> None:
        self._channels.delete(GetChannel(self._channels)(channel_id))


class _Delivery:
    """Tek bir kanala gönderir ve sonucu kanala yazar. Başarılıysa True."""

    def __init__(
        self,
        channels: NotificationChannelRepository,
        cipher: Cipher,
        sender: NotificationSender,
        clock: Clock,
    ) -> None:
        self._channels = channels
        self._cipher = cipher
        self._sender = sender
        self._clock = clock

    def send(self, channel: NotificationChannel, message: Notification) -> bool:
        now = self._clock.now()
        try:
            target = self._cipher.decrypt(channel.target_encrypted)
            self._sender.deliver(channel.type, target, message)
        except Exception as exc:  # bildirim hatası testi bozmasın
            logger.warning("Bildirim gönderilemedi (%s): %s", channel.name, exc)
            channel.record_delivery(now, error=str(exc))
            self._channels.save(channel)
            return False
        channel.record_delivery(now)
        self._channels.save(channel)
        return True


@dataclass
class TrialResult:
    ok: bool
    error: str | None


class SendTestNotification:
    """Kanal ayarını denemek için örnek mesaj gönderir."""

    def __init__(
        self,
        channels: NotificationChannelRepository,
        cipher: Cipher,
        sender: NotificationSender,
        clock: Clock,
    ) -> None:
        self._channels = channels
        self._delivery = _Delivery(channels, cipher, sender, clock)

    def __call__(self, channel_id: int) -> TrialResult:
        channel = GetChannel(self._channels)(channel_id)
        ok = self._delivery.send(channel, sample_notification())
        return TrialResult(ok=ok, error=None if ok else channel.last_error)


class NotifyCollectionRun:
    """Bitmiş bir koleksiyon çalıştırması için isteyen etkin kanallara bildirim gönderir.

    Başarıyla gönderilen bildirim sayısını döndürür.
    """

    def __init__(
        self,
        channels: NotificationChannelRepository,
        test_runs: ApiTestRunRepository,
        cipher: Cipher,
        sender: NotificationSender,
        clock: Clock,
        frontend_url: str,
    ) -> None:
        self._channels = channels
        self._test_runs = test_runs
        self._delivery = _Delivery(channels, cipher, sender, clock)
        self._frontend_url = frontend_url

    def __call__(self, run: CollectionRun) -> int:
        if run.status is None:
            return 0
        wanted = [channel for channel in self._channels.enabled() if channel.wants(run)]
        if not wanted:
            return 0
        message = build_notification(run, self._test_runs.get, self._frontend_url)
        return sum(self._delivery.send(channel, message) for channel in wanted)
