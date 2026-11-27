"""RunNotifier portunun adaptörü: biten koleksiyon çalıştırması için bildirim gönderir.

Bildirim kanallarının kendisi (Slack, Teams, e-posta) ATOP-64'te ayrıca porta taşınacak.
"""

import logging

import httpx
from sqlalchemy.orm import Session

from app.domain.collections import CollectionRun

logger = logging.getLogger(__name__)


class SafeRunNotifier:
    """Bildirimdeki bir sorun çalıştırmanın sonucunu bozmasın: hatayı loglar, yutar."""

    def __init__(self, session: Session, transport: httpx.BaseTransport | None = None) -> None:
        self._session = session
        self._transport = transport

    def notify(self, run: CollectionRun) -> None:
        from app.services.notifications import notify_collection_run

        try:
            notify_collection_run(self._session, run, self._transport)
        except Exception:
            logger.exception("Bildirimler gönderilemedi: çalıştırma %s", run.id)
            self._session.rollback()
