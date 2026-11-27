"""RunNotifier portunun adaptörü: biten koleksiyon çalıştırması için bildirim gönderir."""

import logging

import httpx
from sqlalchemy.orm import Session

from app.domain.collections import CollectionRun

logger = logging.getLogger(__name__)


def notify_use_case(session: Session, transport: httpx.BaseTransport | None = None):
    """NotifyCollectionRun'ı gerçek adaptörlerle kurar."""
    from app.adapters.outbound.clock import SystemClock
    from app.adapters.outbound.notifications.senders import ChannelSender
    from app.adapters.outbound.persistence.notifications import (
        SqlAlchemyNotificationChannelRepository,
    )
    from app.adapters.outbound.persistence.test_runs import SqlAlchemyApiTestRunRepository
    from app.adapters.outbound.security.cipher import FernetCipher
    from app.application.use_cases.notifications import NotifyCollectionRun
    from app.core.config import settings

    return NotifyCollectionRun(
        SqlAlchemyNotificationChannelRepository(session),
        SqlAlchemyApiTestRunRepository(session),
        FernetCipher(),
        ChannelSender(transport),
        SystemClock(),
        settings.frontend_url,
    )


class SafeRunNotifier:
    """Bildirimdeki bir sorun çalıştırmanın sonucunu bozmasın: hatayı loglar, yutar."""

    def __init__(self, session: Session, transport: httpx.BaseTransport | None = None) -> None:
        self._session = session
        self._transport = transport

    def notify(self, run: CollectionRun) -> None:
        try:
            notify_use_case(self._session, self._transport)(run)
        except Exception:
            logger.exception("Bildirimler gönderilemedi: çalıştırma %s", run.id)
            self._session.rollback()
