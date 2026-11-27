"""Geçiş dönemi (ATOP-62): henüz taşınmamış kod için ortam yardımcıları.

Ortam router'ı artık app.adapters.inbound.http.environments içindedir;
bu dosya ATOP-65'te kaldırılacak.
"""

from sqlalchemy.orm import Session

from app.adapters.outbound.persistence.environments import SqlAlchemyEnvironmentRepository
from app.adapters.outbound.security.cipher import FernetCipher
from app.application.use_cases.environments import GetEnvironment
from app.domain.environments import Environment


def get_environment_or_404(db: Session, environment_id: int) -> Environment:
    """Ortamı getirir; yoksa NotFound (HTTP 404) fırlatır."""
    return GetEnvironment(SqlAlchemyEnvironmentRepository(db))(environment_id)


def variable_values(environment: Environment) -> tuple[dict[str, str], list[str]]:
    """Ortamın değişkenlerini çözülmüş halde döndürür: (ad -> değer, gizli değerler)."""
    return environment.resolve_variables(FernetCipher().decrypt)
