"""Bildirim kanalları ve mesajları.

Bir koleksiyon çalıştırması bittiğinde (elle, arka planda ya da zamanlanmış) etkin
kanallara mesaj gönderilir. Varsayılan: sadece başarısız olduğunda.

Kanal tipleri:
    slack    -> Slack "Incoming Webhook" adresi
    teams    -> Microsoft Teams "Incoming Webhook" adresi
    webhook  -> herhangi bir adres; JSON olarak tüm sonuç gönderilir
    email    -> e-posta adres(ler)i (virgülle)

Webhook adresleri gizli sayılır (adresi bilen kanala mesaj atabilir): şifreli saklanır.
Mesajı kanala kimin, nasıl ilettiği (httpx, SMTP) domain'in konusu değildir.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from app.domain.collections import CollectionRun
from app.domain.errors import InvalidInput, SecretUnreadable
from app.domain.testing.runs import ApiTestRun, RunStatus

STATUS_TEXT = {"passed": "GEÇTİ", "failed": "KALDI", "error": "HATA"}
STATUS_ICON = {"passed": "✅", "failed": "❌", "error": "⚠️"}
EMAIL = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")


def check_target(channel_type: str, target: str) -> str:
    """Kanal adresini doğrular ve temizlenmiş halini döndürür."""
    target = target.strip()
    if channel_type == "email":
        addresses = [item.strip() for item in target.split(",") if item.strip()]
        if not addresses or not all(EMAIL.match(item) for item in addresses):
            raise InvalidInput("Geçerli e-posta adres(ler)i girin (virgülle ayırabilirsiniz)")
        return ", ".join(addresses)
    if not target.startswith(("http://", "https://")):
        raise InvalidInput("Webhook adresi http:// veya https:// ile başlamalı")
    return target


@dataclass
class Notification:
    """Kanaldan bağımsız mesaj içeriği."""

    title: str
    text: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(eq=False, kw_only=True)
class NotificationChannel:
    name: str
    type: str
    target_encrypted: str = field(repr=False)
    enabled: bool = True
    # "failure": sadece kalan/hatalı çalıştırmalarda, "always": her çalıştırmada
    notify_on: str = "failure"
    last_sent_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def wants(self, run: CollectionRun) -> bool:
        """Bu çalıştırma için bildirim gönderilmeli mi?"""
        return self.enabled and (self.notify_on == "always" or run.status != RunStatus.PASSED)

    def target_preview(self, decrypt: Callable[[str], str]) -> str:
        """Ekranda gösterilecek hali: webhook adresinin yolu gizlenir."""
        try:
            target = decrypt(self.target_encrypted)
        except SecretUnreadable:
            return "(çözülemedi)"
        if self.type == "email":
            return target
        parts = urlsplit(target)
        return f"{parts.scheme}://{parts.netloc}/****"

    def record_delivery(self, now: datetime, error: str | None = None) -> None:
        """Son gönderimin sonucunu kanala yazar; arayüz kanalın çalışıp çalışmadığını görür."""
        self.last_sent_at = now
        self.last_status = "error" if error else "ok"
        self.last_error = error[:500] if error else None


def sample_notification() -> Notification:
    """Kanal ayarını denemek için örnek mesaj."""
    text = "🔔 API Test Platformu: bu bir deneme bildirimidir. Kanal doğru ayarlanmış."
    return Notification(
        title="Deneme bildirimi", text=text, payload={"event": "test", "text": text}
    )


def _failure_lines(
    run: CollectionRun, find_test_run: Callable[[int], ApiTestRun | None]
) -> list[dict[str, Any]]:
    """Geçemeyen adımlar ve nedenleri: varsa ilk kalan kuralın mesajı."""
    failed: list[dict[str, Any]] = []
    for step in run.steps or []:
        if step.get("status") in ("passed", "skipped"):
            continue
        reason = step.get("message")
        test_run = find_test_run(step["test_run_id"]) if step.get("test_run_id") else None
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


def build_notification(
    run: CollectionRun,
    find_test_run: Callable[[int], ApiTestRun | None],
    frontend_url: str,
) -> Notification:
    """Biten bir koleksiyon çalıştırması için mesaj: başlık, okunur metin ve JSON gövde."""
    status = run.status.value if run.status else "error"
    environment = f" · {run.environment_name}" if run.environment_name else ""
    trigger = " · zamanlanmış" if run.trigger == "schedule" else ""
    title = (
        f"{STATUS_ICON[status]} '{run.collection_name}' {STATUS_TEXT[status]}{environment}{trigger}"
    )
    url = f"{frontend_url}/collections/{run.collection_id}" if run.collection_id else ""

    failed = _failure_lines(run, find_test_run)
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
