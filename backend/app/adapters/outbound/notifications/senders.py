"""NotificationSender portunun adaptörü: Slack/Teams/webhook için HTTP, e-posta için SMTP."""

import smtplib
from email.message import EmailMessage
from typing import Any

import httpx

from app.core.config import settings
from app.domain.notifications import Notification


def send_email(recipients: list[str], message: Notification) -> None:
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


class ChannelSender:
    """Testlerde sahte bir HTTP transport verilebilir."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def deliver(self, channel_type: str, target: str, message: Notification) -> None:
        if channel_type == "email":
            send_email([item.strip() for item in target.split(",") if item.strip()], message)
            return

        if channel_type in ("slack", "teams"):
            body: dict[str, Any] = {"text": message.text}
        else:
            body = {**message.payload, "text": message.text}

        timeout = settings.notification_timeout_seconds
        with httpx.Client(transport=self._transport, timeout=timeout) as client:
            response = client.post(target, json=body)
        if response.status_code >= 400:
            raise ValueError(f"Kanal {response.status_code} döndü: {response.text[:200]}")
