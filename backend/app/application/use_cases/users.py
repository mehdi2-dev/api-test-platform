"""Use case'ler: kullanıcı yönetimi (sadece Admin) ve ilk admin."""

from app.application.ports.users import PasswordHasher, UserRepository
from app.domain.errors import Conflict, NotFound
from app.domain.users import Role, User


class ListUsers:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def __call__(self) -> list[User]:
        return self._users.list_all()


class GetUser:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def __call__(self, user_id: int) -> User:
        user = self._users.get(user_id)
        if user is None:
            raise NotFound("Kullanıcı bulunamadı")
        return user


class CreateUser:
    def __init__(self, users: UserRepository, hasher: PasswordHasher) -> None:
        self._users = users
        self._hasher = hasher

    def __call__(self, *, email: str, full_name: str, password: str, role: Role) -> User:
        email = User.normalize_email(email)
        if self._users.get_by_email(email) is not None:
            raise Conflict("Bu e-posta zaten kayıtlı")

        user = User(
            email=email,
            full_name=full_name,
            hashed_password=self._hasher.hash(password),
            role=role,
            is_active=True,
        )
        self._users.save(user)
        return user


class UpdateUser:
    def __init__(self, users: UserRepository, hasher: PasswordHasher) -> None:
        self._users = users
        self._hasher = hasher

    def __call__(
        self,
        admin: User,
        user_id: int,
        *,
        full_name: str | None = None,
        password: str | None = None,
        role: Role | None = None,
        is_active: bool | None = None,
    ) -> User:
        user = GetUser(self._users)(user_id)
        user.update(
            changed_by=admin,
            full_name=full_name,
            hashed_password=self._hasher.hash(password) if password is not None else None,
            role=role,
            is_active=is_active,
        )
        self._users.save(user)
        return user


class EnsureFirstAdmin:
    """Hiç kullanıcı yoksa ilk admini oluşturur; varsa hiçbir şey yapmaz."""

    def __init__(self, users: UserRepository, hasher: PasswordHasher) -> None:
        self._users = users
        self._hasher = hasher

    def __call__(self, *, email: str, full_name: str, password: str) -> User | None:
        if self._users.count():
            return None

        admin = User(
            email=User.normalize_email(email),
            full_name=full_name,
            hashed_password=self._hasher.hash(password),
            role=Role.ADMIN,
            is_active=True,
        )
        self._users.save(admin)
        return admin
