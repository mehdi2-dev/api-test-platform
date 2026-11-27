"""User domain kuralları: veritabanı ve HTTP olmadan."""

import pytest

from app.domain.errors import ValidationFailed
from app.domain.users import Role, User


def make(email: str = "kisi@apitest.com", role: Role = Role.VIEWER, user_id: int = 2) -> User:
    return User(email=email, full_name="Kişi", hashed_password="x", role=role, id=user_id)


def test_defaults_are_viewer_and_active() -> None:
    user = User(email="a@apitest.com", full_name="A", hashed_password="x")
    assert user.role == Role.VIEWER
    assert user.is_active is True


def test_password_hash_is_not_in_repr() -> None:
    assert "hashed_password" not in repr(make())


def test_email_is_normalized_to_lowercase() -> None:
    assert User.normalize_email("Tester@ApiTest.com") == "tester@apitest.com"


def test_has_role() -> None:
    tester = make(role=Role.TESTER)
    assert tester.has_role(Role.ADMIN, Role.TESTER)
    assert not tester.has_role(Role.ADMIN)


def test_admin_updates_another_user() -> None:
    admin = make("admin@apitest.com", Role.ADMIN, user_id=1)
    user = make(role=Role.TESTER)

    user.update(changed_by=admin, full_name="Yeni Ad", role=Role.VIEWER, is_active=False)

    assert (user.full_name, user.role, user.is_active) == ("Yeni Ad", Role.VIEWER, False)


def test_fields_not_given_stay_the_same() -> None:
    admin = make("admin@apitest.com", Role.ADMIN, user_id=1)
    user = make(role=Role.TESTER)

    user.update(changed_by=admin, full_name="Yeni Ad")

    assert (user.role, user.is_active, user.hashed_password) == (Role.TESTER, True, "x")


def test_admin_cannot_demote_self() -> None:
    admin = make("admin@apitest.com", Role.ADMIN, user_id=1)

    with pytest.raises(ValidationFailed, match="Kendi rolünüzü"):
        admin.update(changed_by=admin, role=Role.VIEWER)
    assert admin.role == Role.ADMIN


def test_admin_cannot_deactivate_self() -> None:
    admin = make("admin@apitest.com", Role.ADMIN, user_id=1)

    with pytest.raises(ValidationFailed, match="pasifleştiremezsiniz"):
        admin.update(changed_by=admin, is_active=False)
    assert admin.is_active is True


def test_admin_can_rename_self_and_keep_admin_role() -> None:
    admin = make("admin@apitest.com", Role.ADMIN, user_id=1)

    admin.update(changed_by=admin, full_name="Yönetici", role=Role.ADMIN, is_active=True)

    assert admin.full_name == "Yönetici"
