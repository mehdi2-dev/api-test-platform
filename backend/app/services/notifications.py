"""Geçiş dönemi (ATOP-64): bildirimler artık use case'lerde (NotifyCollectionRun) ve
adaptörlerde (ChannelSender: HTTP ve SMTP). ATOP-65'te kaldırılacak.

smtplib ve settings burada da görünür kalır; eski testler e-posta gönderimini bu modül
üzerinden taklit ediyor.
"""

import smtplib  # noqa: F401

import httpx
from sqlalchemy.orm import Session

from app.adapters.outbound.notifications.run_notifier import notify_use_case
from app.core.config import settings  # noqa: F401
from app.domain.collections import CollectionRun
from app.domain.notifications import Notification, build_notification, sample_notification  # noqa: F401


def notify_collection_run(
    db: Session, run: CollectionRun, transport: httpx.BaseTransport | None = None
) -> int:
    """Bitmiş bir koleksiyon çalıştırması için etkin kanallara bildirim gönderir."""
    return notify_use_case(db, transport)(run)
