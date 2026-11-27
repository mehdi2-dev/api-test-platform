"""Test adaptörleri: portların bellekte çalışan sahte uygulamaları.

Use case'ler bunlarla veritabanı, bcrypt veya JWT olmadan, milisaniyeler içinde test edilir.
"""

from typing import Any

from app.application.errors import InvalidToken
from app.application.ports.auth import TokenKind, TokenPair
from app.domain.api_definitions import ApiDefinition
from app.domain.environments import Environment
from app.domain.errors import SecretUnreadable
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

    def __init__(self, outcome: SendOutcome) -> None:
        self.outcome = outcome
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
        return self.outcome


class InMemoryApiTestRunRepository:
    def __init__(self) -> None:
        self.items: list[ApiTestRun] = []

    def add(self, run: ApiTestRun) -> None:
        run.id = len(self.items) + 1
        self.items.append(run)
