"""Bildirimler: kanal kuralları, mesaj içeriği ve gönderim; sahte gönderici ile.

Gerçek Slack/Teams/SMTP yok: NotificationSender portuna mesajları kaydeden bir sahte takılı.
"""

from datetime import UTC, datetime

import pytest

from app.application.use_cases.notifications import (
    CreateChannel,
    NotifyCollectionRun,
    SendTestNotification,
)
from app.domain.collections import CollectionRun
from app.domain.errors import InvalidInput
from app.domain.notifications import NotificationChannel, build_notification, check_target
from app.domain.testing.runs import ApiTestRun, RunStatus
from tests.fakes import (
    FakeCipher,
    FixedClock,
    InMemoryApiTestRunRepository,
    InMemoryChannelRepository,
    RecordingSender,
)

NOW = datetime(2030, 1, 7, 6, 0, tzinfo=UTC)


def finished_run(status: RunStatus, **changes) -> CollectionRun:
    data = {
        "id": 9,
        "collection_id": 3,
        "collection_name": "Gece testi",
        "environment_name": "Stage",
        "status": status,
        "state": "completed",
        "trigger": "schedule",
        "total_steps": 2,
        "passed_steps": 1,
        "elapsed_ms": 120.0,
        "steps": [
            {"api_name": "Giriş", "method": "POST", "status": "passed", "test_run_id": 1},
            {"api_name": "Profil", "method": "GET", "status": "failed", "test_run_id": 2},
        ],
        **changes,
    }
    return CollectionRun(**data)


@pytest.fixture
def test_runs() -> InMemoryApiTestRunRepository:
    repo = InMemoryApiTestRunRepository()
    for status_code, results in [
        (200, []),
        (401, [{"passed": False, "message": "Beklenen 200, gelen 401", "actual": "401"}]),
    ]:
        repo.add(
            ApiTestRun(
                api_name="x",
                method="GET",
                status=RunStatus.PASSED,
                status_code=status_code,
                assertion_results=results,
            )
        )
    return repo


@pytest.fixture
def channels() -> InMemoryChannelRepository:
    repo = InMemoryChannelRepository()
    create = CreateChannel(repo, FakeCipher())
    create(
        name="Slack ",
        channel_type="slack",
        target="https://hooks.slack.com/x/y",
        enabled=True,
        notify_on="failure",
    )
    create(
        name="Webhook",
        channel_type="webhook",
        target="https://hata.example.com/z",
        enabled=True,
        notify_on="always",
    )
    create(
        name="Kapalı",
        channel_type="teams",
        target="https://teams.example.com/k",
        enabled=False,
        notify_on="always",
    )
    return repo


def notify(channels, test_runs, sender) -> NotifyCollectionRun:
    return NotifyCollectionRun(
        channels, test_runs, FakeCipher(), sender, FixedClock(NOW), "http://localhost:5173"
    )


# --- Domain ---


def test_targets_are_validated_and_cleaned() -> None:
    assert check_target("email", " a@firma.com ,b@firma.com ") == "a@firma.com, b@firma.com"
    with pytest.raises(InvalidInput, match="e-posta"):
        check_target("email", "posta-degil")
    with pytest.raises(InvalidInput, match="http"):
        check_target("slack", "hooks.slack.com/x")


def test_webhook_path_is_hidden_in_preview() -> None:
    channel = NotificationChannel(
        name="S", type="slack", target_encrypted="enc:https://hooks.slack.com/gizli/yol"
    )
    assert channel.target_preview(FakeCipher().decrypt) == "https://hooks.slack.com/****"
    assert (
        NotificationChannel(name="B", type="slack", target_encrypted="bozuk").target_preview(
            FakeCipher().decrypt
        )
        == "(çözülemedi)"
    )


def test_message_names_the_first_failed_rule(test_runs) -> None:
    message = build_notification(finished_run(RunStatus.FAILED), test_runs.get, "http://app")

    assert message.title == "❌ 'Gece testi' KALDI · Stage · zamanlanmış"
    assert "• GET Profil [401]: Beklenen 200, gelen 401 (gelen: 401)" in message.text
    assert "Detay: http://app/collections/3" in message.text
    assert [step["api_name"] for step in message.payload["failed_steps"]] == ["Profil"]


# --- Use case ---


def test_failed_run_goes_to_enabled_channels(channels, test_runs) -> None:
    sender = RecordingSender()

    sent = notify(channels, test_runs, sender)(finished_run(RunStatus.FAILED))

    assert sent == 2
    assert [(kind, target) for kind, target, _ in sender.sent] == [
        ("slack", "https://hooks.slack.com/x/y"),
        ("webhook", "https://hata.example.com/z"),
    ]


def test_passed_run_only_goes_to_always_channels(channels, test_runs) -> None:
    sender = RecordingSender()

    notify(channels, test_runs, sender)(finished_run(RunStatus.PASSED))

    assert [kind for kind, _, _ in sender.sent] == ["webhook"]


def test_broken_channel_is_recorded_and_others_still_get_the_message(channels, test_runs) -> None:
    sender = RecordingSender(fail_for={"slack"})

    sent = notify(channels, test_runs, sender)(finished_run(RunStatus.FAILED))

    slack, webhook = channels.get(1), channels.get(2)
    assert sent == 1
    assert (slack.last_status, slack.last_error, slack.last_sent_at) == (
        "error",
        "Kanal 404 döndü",
        NOW,
    )
    assert (webhook.last_status, webhook.last_error) == ("ok", None)


def test_unfinished_run_sends_nothing(channels, test_runs) -> None:
    sender = RecordingSender()
    assert notify(channels, test_runs, sender)(finished_run(None)) == 0
    assert sender.sent == []


def test_trial_notification_reports_the_error(channels) -> None:
    result = SendTestNotification(
        channels, FakeCipher(), RecordingSender(fail_for={"slack"}), FixedClock(NOW)
    )(1)

    assert (result.ok, result.error) == (False, "Kanal 404 döndü")
