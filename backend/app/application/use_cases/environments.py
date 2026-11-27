"""Use case'ler: ortam yönetimi."""

from app.application.ports.environments import EnvironmentRepository
from app.application.ports.security import Cipher
from app.domain.environments import Environment, VariableInput
from app.domain.errors import Conflict, NotFound


class _Unchanged:
    """'Bu alan gönderilmedi' işareti (None ise 'boşalt' demektir)."""

    def __repr__(self) -> str:
        return "UNCHANGED"


UNCHANGED = _Unchanged()


def _ensure_name_free(
    environments: EnvironmentRepository, name: str, own_id: int | None = None
) -> None:
    other = environments.get_by_name(name)
    if other is not None and other.id != own_id:
        raise Conflict(f"'{name}' adında bir ortam zaten var")


class ListEnvironments:
    def __init__(self, environments: EnvironmentRepository) -> None:
        self._environments = environments

    def __call__(self) -> list[Environment]:
        return self._environments.list_all()


class GetEnvironment:
    def __init__(self, environments: EnvironmentRepository) -> None:
        self._environments = environments

    def __call__(self, environment_id: int) -> Environment:
        environment = self._environments.get(environment_id)
        if environment is None:
            raise NotFound("Ortam bulunamadı")
        return environment


class CreateEnvironment:
    def __init__(self, environments: EnvironmentRepository, cipher: Cipher) -> None:
        self._environments = environments
        self._cipher = cipher

    def __call__(
        self,
        *,
        name: str,
        description: str | None,
        is_production: bool,
        variables: list[VariableInput],
    ) -> Environment:
        _ensure_name_free(self._environments, name)
        environment = Environment(name=name, description=description, is_production=is_production)
        environment.replace_variables(variables, self._cipher.encrypt)
        self._environments.save(environment)
        return environment


class UpdateEnvironment:
    """Sadece verilen alanlar değişir; variables verilirse listenin tamamı yerine geçer."""

    def __init__(self, environments: EnvironmentRepository, cipher: Cipher) -> None:
        self._environments = environments
        self._cipher = cipher

    def __call__(
        self,
        environment_id: int,
        *,
        name: str | None = None,
        description: str | None | _Unchanged = UNCHANGED,
        is_production: bool | None = None,
        variables: list[VariableInput] | None = None,
    ) -> Environment:
        environment = GetEnvironment(self._environments)(environment_id)

        if name is not None:
            _ensure_name_free(self._environments, name, own_id=environment.id)
            environment.name = name
        if not isinstance(description, _Unchanged):
            environment.description = description
        if is_production is not None:
            environment.is_production = is_production
        if variables is not None:
            environment.replace_variables(variables, self._cipher.encrypt)

        self._environments.save(environment)
        return environment


class DeleteEnvironment:
    def __init__(self, environments: EnvironmentRepository) -> None:
        self._environments = environments

    def __call__(self, environment_id: int) -> None:
        self._environments.delete(GetEnvironment(self._environments)(environment_id))
