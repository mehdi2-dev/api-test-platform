"""HTTP katmanının ortak bağımlılıkları: adaptörleri kurar, oturum açmış kullanıcıyı bulur.

Kullanım:
    @router.get("/x")
    def x(user: CurrentUser): ...                      # sadece giriş yapmış olmak yeter

    @router.post("/y", dependencies=[Depends(require_roles(Role.ADMIN, Role.TESTER))])
    def y(): ...                                       # admin veya tester olmalı
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.adapters.outbound.persistence.api_definitions import SqlAlchemyApiDefinitionRepository
from app.adapters.outbound.persistence.collections import (
    SqlAlchemyCollectionRepository,
    SqlAlchemyCollectionRunRepository,
)
from app.adapters.outbound.persistence.environments import SqlAlchemyEnvironmentRepository
from app.adapters.outbound.persistence.test_runs import SqlAlchemyApiTestRunRepository
from app.adapters.outbound.persistence.users import SqlAlchemyUserRepository
from app.adapters.outbound.security.cipher import FernetCipher
from app.adapters.outbound.security.passwords import BcryptPasswordHasher
from app.adapters.outbound.security.tokens import JwtTokenService
from app.application.errors import AuthenticationFailed
from app.application.ports.api_definitions import ApiDefinitionRepository
from app.application.ports.auth import TokenService
from app.application.ports.collections import CollectionRepository, CollectionRunRepository
from app.application.ports.environments import EnvironmentRepository
from app.application.ports.security import Cipher
from app.application.ports.testing import ApiTestRunRepository
from app.application.ports.users import PasswordHasher, UserRepository
from app.application.use_cases.auth import AuthenticateUser
from app.db.session import get_db
from app.domain.users import Role, User

bearer_scheme = HTTPBearer(auto_error=False, description="Giriş yapınca aldığınız access token")

DbSession = Annotated[Session, Depends(get_db)]


# --- Portlara takılan adaptörler (testlerde dependency_overrides ile değiştirilebilir) ---


def get_user_repository(db: DbSession) -> UserRepository:
    return SqlAlchemyUserRepository(db)


def get_password_hasher() -> PasswordHasher:
    return BcryptPasswordHasher()


def get_token_service() -> TokenService:
    return JwtTokenService.from_settings()


def get_environment_repository(db: DbSession) -> EnvironmentRepository:
    return SqlAlchemyEnvironmentRepository(db)


def get_api_definition_repository(db: DbSession) -> ApiDefinitionRepository:
    return SqlAlchemyApiDefinitionRepository(db)


def get_test_run_repository(db: DbSession) -> ApiTestRunRepository:
    return SqlAlchemyApiTestRunRepository(db)


def get_collection_repository(db: DbSession) -> CollectionRepository:
    return SqlAlchemyCollectionRepository(db)


def get_collection_run_repository(db: DbSession) -> CollectionRunRepository:
    return SqlAlchemyCollectionRunRepository(db)


def get_cipher() -> Cipher:
    return FernetCipher()


Users = Annotated[UserRepository, Depends(get_user_repository)]
Hasher = Annotated[PasswordHasher, Depends(get_password_hasher)]
Tokens = Annotated[TokenService, Depends(get_token_service)]
Environments = Annotated[EnvironmentRepository, Depends(get_environment_repository)]
CipherDep = Annotated[Cipher, Depends(get_cipher)]
ApiDefinitions = Annotated[ApiDefinitionRepository, Depends(get_api_definition_repository)]
TestRuns = Annotated[ApiTestRunRepository, Depends(get_test_run_repository)]
Collections = Annotated[CollectionRepository, Depends(get_collection_repository)]
CollectionRuns = Annotated[CollectionRunRepository, Depends(get_collection_run_repository)]


# --- Oturum ve yetki ---


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    users: Users,
    tokens: Tokens,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise _unauthorized("Bu işlem için giriş yapmanız gerekiyor")
    try:
        return AuthenticateUser(users, tokens)(credentials.credentials)
    except AuthenticationFailed as exc:
        raise _unauthorized(exc.message) from exc


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: Role) -> Callable[[User], User]:
    """Kullanıcının rolü izin verilenler arasında değilse 403 döndürür."""

    def checker(user: CurrentUser) -> User:
        if not user.has_role(*allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu işlem için yetkiniz yok",
            )
        return user

    return checker
