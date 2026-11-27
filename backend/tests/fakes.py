"""Test adaptörleri: portların bellekte çalışan sahte uygulamaları.

Use case'ler bunlarla veritabanı, bcrypt veya JWT olmadan, milisaniyeler içinde test edilir.
"""

from datetime import datetime
from typing import Any

from app.application.errors import InvalidToken
from app.application.ports.auth import TokenKind, TokenPair
from app.domain.api_definitions import ApiDefinition
from app.domain.collections import Collection, CollectionRun
from app.domain.environments import Environment
from app.domain.errors import SecretUnreadable
from app.domain.notifications import Notification, NotificationChannel
from app.domain.schedules import Schedule
from app.domain.testing.runs import ApiTestRun, SendOutcome
from app.domain.users import User


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[int, User] = {}
        self._next_id = 1

    def get(self, user_id: int) -> User | None:
        return self.items.get(user_id)

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self.items.values() if u.email == email), None)

    def list_all(self) -> list[User]:
        return [self.items[key] for key in sorted(self.items)]

    def count(self) -> int:
        return len(self.items)

    def save(self, user: User) -> None:
        if user.id is None:
            user.id = self._next_id
            self._next_id += 1
        self.items[user.id] = user


class PlainPasswordHasher:
    """Gerçek özet yerine okunabilir bir önek: 'hashed:<şifre>'."""

    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, hashed_password: str) -> bool:
        return hashed_password == f"hashed:{password}"


class FakeTokenService:
    """Token olarak '<tür>:<kullanıcı id>' metnini kullanır."""

    def issue(self, user: User) -> TokenPair:
        return TokenPair(
            access_token=f"access:{user.id}", refresh_token=f"refresh:{user.id}", expires_in=60
        )

    def user_id_from(self, token: str, kind: TokenKind) -> int:
        token_kind, _, user_id = token.partition(":")
        if token_kind != kind or not user_id.isdigit():
            raise InvalidToken("geçersiz")
        return int(user_id)


class FakeLoginLimiter:
    """Belirtilen sayıda hatalı denemeden sonra kilitlenen basit sayaç."""

    def __init__(self, max_attempts: int = 3, lock_seconds: int = 600) -> None:
        self.max_attempts = max_attempts
        self.lock_seconds = lock_seconds
        self.failures: dict[str, int] = {}

    def retry_after(self, key: str) -> int:
        return self.lock_seconds if self.failures.get(key, 0) >= self.max_attempts else 0

    def failed(self, key: str) -> None:
        self.failures[key] = self.failures.get(key, 0) + 1

    def succeeded(self, key: str) -> None:
        self.failures.pop(key, None)


class InMemoryEnvironmentRepository:
    def __init__(self) -> None:
        self.items: dict[int, Environment] = {}
        self._next_id = 1

    def get(self, environment_id: int) -> Environment | None:
        return self.items.get(environment_id)

    def get_by_name(self, name: str) -> Environment | None:
        return next((e for e in self.items.values() if e.name == name), None)

    def list_all(self) -> list[Environment]:
        return sorted(self.items.values(), key=lambda e: (e.is_production, e.name))

    def save(self, environment: Environment) -> None:
        if environment.id is None:
            environment.id = self._next_id
            self._next_id += 1
        self.items[environment.id] = environment

    def delete(self, environment: Environment) -> None:
        self.items.pop(environment.id, None)


class FakeCipher:
    """Şifreleme yerine okunabilir bir önek: 'enc:<değer>'."""

    def encrypt(self, plain: str) -> str:
        return f"enc:{plain}"

    def decrypt(self, token: str) -> str:
        if not token.startswith("enc:"):
            raise SecretUnreadable("Şifreli veri çözülemedi")
        return token.removeprefix("enc:")


class InMemoryApiDefinitionRepository:
    def __init__(self) -> None:
        self.items: dict[int, ApiDefinition] = {}
        self._next_id = 1

    def get(self, api_id: int) -> ApiDefinition | None:
        return self.items.get(api_id)

    def search(self, name_contains: str | None = None) -> list[ApiDefinition]:
        found = [
            api
            for api in self.items.values()
            if not name_contains or name_contains.lower() in api.name.lower()
        ]
        return sorted(found, key=lambda api: (api.name, api.id))

    def save(self, api: ApiDefinition) -> None:
        if api.id is None:
            api.id = self._next_id
            self._next_id += 1
        self.items[api.id] = api

    def delete(self, api: ApiDefinition) -> None:
        self.items.pop(api.id, None)


class FakeApiSender:
    """Ağa çıkmadan, önceden verilen sonucu döndüren gönderici; çağrıları kaydeder."""

    def __init__(self, *outcomes: SendOutcome) -> None:
        """Her çağrıda sıradaki sonucu döner; sonuncusu tekrarlanır."""
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def send(
        self,
        api: ApiDefinition,
        auth: dict[str, Any],
        *,
        variables: dict[str, str],
        secrets: list[str],
        environment_name: str | None,
    ) -> SendOutcome:
        self.calls.append(
            {
                "api": api,
                "auth": auth,
                "variables": variables,
                "secrets": secrets,
                "environment_name": environment_name,
            }
        )
        return self.outcomes[min(len(self.calls), len(self.outcomes)) - 1]


class InMemoryApiTestRunRepository:
    def __init__(self) -> None:
        self.items: list[ApiTestRun] = []

    def add(self, run: ApiTestRun) -> None:
        run.id = len(self.items) + 1
        self.items.append(run)

    def for_collection_run(self, collection_run_id: int) -> list[ApiTestRun]:
        return [run for run in self.items if run.collection_run_id == collection_run_id]

    def get(self, run_id: int) -> ApiTestRun | None:
        return next((run for run in self.items if run.id == run_id), None)

    def recent(self, *, api_id=None, status=None, limit: int = 20) -> list[ApiTestRun]:
        found = [
            run
            for run in self.items
            if (api_id is None or run.api_definition_id == api_id)
            and (status is None or run.status == status)
        ]
        return sorted(found, key=lambda run: (run.created_at, run.id), reverse=True)[:limit]

    def search(self, filters, *, offset: int, limit: int) -> tuple[int, list[ApiTestRun]]:
        found = self.recent(limit=len(self.items))
        if filters.name_contains:
            found = [r for r in found if filters.name_contains.lower() in r.api_name.lower()]
        return len(found), found[offset : offset + limit]

    def since(self, moment: datetime) -> list[ApiTestRun]:
        return [run for run in self.items if run.created_at >= moment]

    def last_passed_before(self, api_definition_id: int, run_id: int) -> ApiTestRun | None:
        earlier = [
            run
            for run in self.items
            if run.api_definition_id == api_definition_id
            and run.status == "passed"
            and run.id < run_id
        ]
        return max(earlier, key=lambda run: run.id, default=None)


class InMemoryCollectionRepository:
    def __init__(self) -> None:
        self.items: dict[int, Collection] = {}

    def get(self, collection_id: int) -> Collection | None:
        return self.items.get(collection_id)

    def get_by_name(self, name: str) -> Collection | None:
        return next((c for c in self.items.values() if c.name == name), None)

    def list_all(self) -> list[Collection]:
        return sorted(self.items.values(), key=lambda c: c.name)

    def save(self, collection: Collection) -> None:
        if collection.id is None:
            collection.id = max(self.items, default=0) + 1
        self.items[collection.id] = collection

    def delete(self, collection: Collection) -> None:
        self.items.pop(collection.id, None)


class InMemoryCollectionRunRepository:
    def __init__(self) -> None:
        self.items: dict[int, CollectionRun] = {}

    def get(self, run_id: int) -> CollectionRun | None:
        return self.items.get(run_id)

    def save(self, run: CollectionRun) -> None:
        if run.id is None:
            run.id = len(self.items) + 1
        self.items[run.id] = run

    def latest_for(self, collection_id: int) -> CollectionRun | None:
        recent = self.recent_for(collection_id, 1)
        return recent[0] if recent else None

    def recent_for(self, collection_id: int, limit: int) -> list[CollectionRun]:
        runs = [r for r in self.items.values() if r.collection_id == collection_id]
        return sorted(runs, key=lambda r: r.id, reverse=True)[:limit]

    def recent(self, limit: int) -> list[CollectionRun]:
        return sorted(self.items.values(), key=lambda run: run.id, reverse=True)[:limit]

    def discard_changes(self) -> None:
        pass


class RecordingNotifier:
    """Bildirim göndermek yerine hangi çalıştırmalar için çağrıldığını kaydeder."""

    def __init__(self) -> None:
        self.notified: list[CollectionRun] = []

    def notify(self, run: CollectionRun) -> None:
        self.notified.append(run)


class FixedClock:
    """Hep aynı anı döndüren saat."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class InMemoryScheduleRepository:
    """Kaydederken ilişkileri (collection, environment) de bağlar; veritabanı bunu kendisi yapar."""

    def __init__(
        self,
        runs: InMemoryCollectionRunRepository,
        collections: InMemoryCollectionRepository,
        environments: InMemoryEnvironmentRepository,
    ) -> None:
        self.items: dict[int, Schedule] = {}
        self._runs = runs
        self._collections = collections
        self._environments = environments

    def get(self, schedule_id: int) -> Schedule | None:
        return self.items.get(schedule_id)

    def list_all(self) -> list[Schedule]:
        return list(self.items.values())

    def save(self, schedule: Schedule) -> None:
        if schedule.id is None:
            schedule.id = max(self.items, default=0) + 1
        schedule.collection = self._collections.get(schedule.collection_id)
        schedule.environment = (
            self._environments.get(schedule.environment_id) if schedule.environment_id else None
        )
        self.items[schedule.id] = schedule

    def delete(self, schedule: Schedule) -> None:
        self.items.pop(schedule.id, None)

    def due(self, now: datetime) -> list[Schedule]:
        return [
            s for s in self.items.values() if s.enabled and s.next_run_at and s.next_run_at <= now
        ]

    def stage_run(self, run: CollectionRun) -> None:
        self._runs.save(run)

    def commit(self) -> None:
        pass


class InMemoryChannelRepository:
    def __init__(self) -> None:
        self.items: dict[int, NotificationChannel] = {}

    def get(self, channel_id: int) -> NotificationChannel | None:
        return self.items.get(channel_id)

    def list_all(self) -> list[NotificationChannel]:
        return sorted(self.items.values(), key=lambda channel: channel.name)

    def enabled(self) -> list[NotificationChannel]:
        return [channel for channel in self.items.values() if channel.enabled]

    def save(self, channel: NotificationChannel) -> None:
        if channel.id is None:
            channel.id = max(self.items, default=0) + 1
        self.items[channel.id] = channel

    def delete(self, channel: NotificationChannel) -> None:
        self.items.pop(channel.id, None)


class RecordingSender:
    """Mesajları göndermek yerine kaydeder; fail_for'daki kanal tipleri 404 hatası verir."""

    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.fail_for = fail_for or set()
        self.sent: list[tuple[str, str, Notification]] = []

    def deliver(self, channel_type: str, target: str, message: Notification) -> None:
        if channel_type in self.fail_for:
            raise ValueError("Kanal 404 döndü")
        self.sent.append((channel_type, target, message))
