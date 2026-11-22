"""Başarısız test bildirimleri (ATOP-48).

notify_collection_run() koleksiyon çalıştırması bitince çağrılır. Bir kanal hata verirse
diğerleri yine denenir ve hata kanalın kendisine yazılır (last_status / last_error);
böylece bildirim sorunu testin sonucunu asla bozmaz.
"""

import logging
import smtplib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_text
from app.models.collection import CollectionRun
from app.models.notification import NotificationChannel
from app.models.test_run import ApiTestRun, RunStatus

logger = logging.getLogger(__name__)

STATUS_TEXT = {"passed": "GEÇTİ", "failed": "KALDI", "error": "HATA"}
STATUS_ICON = {"passed": "✅", "failed": "❌", "error": "⚠️"}


@dataclass
class Notification:
    """Kanaldan bağımsız mesaj içeriği."""

    title: str
    text: str
    payload: dict[str, Any] = field(default_factory=dict)


def _failure_lines(db: Session, run: CollectionRun) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for step in run.steps or []:
        if step.get("status") in ("passed", "skipped"):
            continue
        reason = step.get("message")
        test_run = db.get(ApiTestRun, step["test_run_id"]) if step.get("test_run_id") else None
        if test_run is not None:
            first = next(
                (item for item in test_run.assertion_results or [] if not item.get("passed")),
                None,
            )
            if first is not None:
                actual = f" (gelen: {first['actual']})" if first.get("actual") is not None else ""
                reason = f"{first['message']}{actual}"
        failed.append(
            {
                "api_name": step.get("api_name"),
                "method": step.get("method"),
                "status": step.get("status"),
                "status_code": test_run.status_code if test_run else None,
                "reason": reason,
                "test_run_id": step.get("test_run_id"),
            }
        )
    return failed


def build_notification(db: Session, run: CollectionRun) -> Notification:
    status = run.status.value if run.status else "error"
    environment = f" · {run.environment_name}" if run.environment_name else ""
    trigger = " · zamanlanmış" if run.trigger == "schedule" else ""
    title = (
        f"{STATUS_ICON[status]} '{run.collection_name}' {STATUS_TEXT[status]}{environment}{trigger}"
    )
    url = f"{settings.frontend_url}/collections/{run.collection_id}" if run.collection_id else ""

    failed = _failure_lines(db, run)
    lines = [title, f"{run.passed_steps}/{run.total_steps} adım geçti · {run.elapsed_ms:g} ms"]
    if run.error:
        lines.append(f"Neden: {run.error}")
    for item in failed[:10]:
        code = f" [{item['status_code']}]" if item["status_code"] else ""
        lines.append(f"• {item['method']} {item['api_name']}{code}: {item['reason']}")
    if url:
        lines.append(f"Detay: {url}")

    payload = {
        "event": "collection_run.completed",
        "status": status,
        "collection": {"id": run.collection_id, "name": run.collection_name},
        "environment": run.environment_name,
        "trigger": run.trigger,
        "run_id": run.id,
        "passed_steps": run.passed_steps,
        "total_steps": run.total_steps,
        "elapsed_ms": run.elapsed_ms,
        "failed_steps": failed,
        "error": run.error,
        "url": url,
    }
    return Notification(title=title, text="\n".join(lines), payload=payload)


def sample_notification() -> Notification:
    """Kanal ayarını denemek için örnek mesaj."""
    text = "🔔 API Test Platformu: bu bir deneme bildirimidir. Kanal doğru ayarlanmış."
    return Notification(
        title="Deneme bildirimi", text=text, payload={"event": "test", "text": text}
    )


def _send_email(recipients: list[str], message: Notification) -> None:
    if not settings.smtp_host:
        raise ValueError("SMTP ayarlı değil (.env içinde SMTP_HOST)")
    email = EmailMessage()
    email["Subject"] = message.title
    email["From"] = settings.smtp_from
    email["To"] = ", ".join(recipients)
    email.set_content(message.text)
    timeout = settings.notification_timeout_seconds
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(email)


def deliver(
    channel: NotificationChannel,
    message: Notification,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Tek bir kanala gönderir; başarısızsa istisna fırlatır."""
    target = decrypt_text(channel.target_encrypted)
    if channel.type == "email":
        _send_email([item.strip() for item in target.split(",") if item.strip()], message)
        return

    if channel.type in ("slack", "teams"):
        body: dict[str, Any] = {"text": message.text}
    else:
        body = {**message.payload, "text": message.text}

    with httpx.Client(transport=transport, timeout=settings.notification_timeout_seconds) as client:
        response = client.post(target, json=body)
    if response.status_code >= 400:
        raise ValueError(f"Kanal {response.status_code} döndü: {response.text[:200]}")


def send_to_channel(
    db: Session,
    channel: NotificationChannel,
    message: Notification,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    """Gönderir ve sonucu kanala yazar. Başarılıysa True."""
    channel.last_sent_at = datetime.now(UTC)
    try:
        deliver(channel, message, transport)
    except Exception as exc:  # bildirim hatası testi bozmasın
        logger.warning("Bildirim gönderilemedi (%s): %s", channel.name, exc)
        channel.last_status = "error"
        channel.last_error = str(exc)[:500]
        db.commit()
        return False
    channel.last_status = "ok"
    channel.last_error = None
    db.commit()
    return True


def notify_collection_run(
    db: Session, run: CollectionRun, transport: httpx.BaseTransport | None = None
) -> int:
    """Bitmiş bir koleksiyon çalıştırması için etkin kanallara bildirim gönderir.

    Gönderilen (başarılı) bildirim sayısını döndürür.
    """
    if run.status is None:
        return 0
    channels = db.scalars(
        select(NotificationChannel).where(NotificationChannel.enabled.is_(True))
    ).all()
    wanted = [
        channel
        for channel in channels
        if channel.notify_on == "always" or run.status != RunStatus.PASSED
    ]
    if not wanted:
        return 0

    message = build_notification(db, run)
    return sum(send_to_channel(db, channel, message, transport) for channel in wanted)
