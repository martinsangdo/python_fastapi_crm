"""
tests/test_service_users.py
---------------------------
SERVICE-LAYER tests for users_service.py.

These exercise the Users administration BUSINESS RULES directly (no HTTP):
email uniqueness, role resolution, the self-protection and "last active admin"
safety nets, and the typed errors (NotFoundError / ConflictError /
BusinessRuleError) the router maps onto 404 / 409 / 400.
"""

import uuid

import pytest

import users_service as service
from security import verify_password
from users_schemas import UserAdminCreate, UserAdminUpdate


# ---------------------------------------------------------------------------
# get_user_or_404 / to_detail
# ---------------------------------------------------------------------------

def test_get_user_or_404_found(db_session, seed):
    admin = seed["users"]["admin"]
    assert service.get_user_or_404(db_session, admin.id).id == admin.id


def test_get_user_or_404_missing_raises(db_session, seed):
    with pytest.raises(service.NotFoundError):
        service.get_user_or_404(db_session, uuid.uuid4())


def test_to_detail_includes_role_and_permissions(db_session, seed):
    sales = seed["users"]["sales"]
    detail = service.to_detail(db_session, sales)
    assert detail.email == "sales@example.com"
    assert detail.role.code == "SALES"
    # Effective permission codes come from the role, sorted.
    assert detail.permissions == ["customers.read", "dashboard.view"]


def test_to_detail_handles_user_without_role(db_session, seed):
    norole = seed["users"]["norole"]
    detail = service.to_detail(db_session, norole)
    assert detail.role is None
    assert detail.permissions == []


# ---------------------------------------------------------------------------
# create_user_admin
# ---------------------------------------------------------------------------

def test_create_user_admin_success(db_session, seed):
    sales_role = seed["roles"]["sales"]
    data = UserAdminCreate(
        email="Fresh@Example.com",
        full_name="  Fresh Person  ",
        password="secret123",
        role_id=sales_role.id,
        is_active=True,
    )
    user = service.create_user_admin(db_session, data)
    assert user.email == "fresh@example.com"  # normalised
    assert user.full_name == "Fresh Person"   # stripped
    assert user.role_id == sales_role.id
    assert verify_password("secret123", user.password_hash)


def test_create_user_admin_without_role(db_session, seed):
    data = UserAdminCreate(
        email="norole2@example.com",
        full_name="No Role Two",
        password="secret123",
    )
    user = service.create_user_admin(db_session, data)
    assert user.role_id is None


def test_create_user_admin_duplicate_email_conflict(db_session, seed):
    data = UserAdminCreate(
        email="admin@example.com",
        full_name="Copycat",
        password="secret123",
    )
    with pytest.raises(service.ConflictError):
        service.create_user_admin(db_session, data)


def test_create_user_admin_unknown_role_not_found(db_session, seed):
    data = UserAdminCreate(
        email="ghost@example.com",
        full_name="Ghost",
        password="secret123",
        role_id=uuid.uuid4(),  # no such role
    )
    with pytest.raises(service.NotFoundError):
        service.create_user_admin(db_session, data)


# ---------------------------------------------------------------------------
# update_user_admin
# ---------------------------------------------------------------------------

def test_update_user_admin_changes_name(db_session, seed):
    admin = seed["users"]["admin"]
    sales = seed["users"]["sales"]
    updated = service.update_user_admin(
        db_session, admin, sales.id, UserAdminUpdate(full_name="  Renamed  ")
    )
    assert updated.full_name == "Renamed"


def test_update_user_admin_changes_role(db_session, seed):
    admin = seed["users"]["admin"]
    norole = seed["users"]["norole"]
    sales_role = seed["roles"]["sales"]
    updated = service.update_user_admin(
        db_session, admin, norole.id, UserAdminUpdate(role_id=sales_role.id)
    )
    assert updated.role_id == sales_role.id


def test_update_user_admin_clears_role(db_session, seed):
    admin = seed["users"]["admin"]
    sales = seed["users"]["sales"]
    # role_id explicitly set to None clears the role.
    updated = service.update_user_admin(
        db_session, admin, sales.id, UserAdminUpdate(role_id=None)
    )
    assert updated.role_id is None


def test_update_user_admin_unknown_role_not_found(db_session, seed):
    admin = seed["users"]["admin"]
    sales = seed["users"]["sales"]
    with pytest.raises(service.NotFoundError):
        service.update_user_admin(
            db_session, admin, sales.id, UserAdminUpdate(role_id=uuid.uuid4())
        )


def test_update_deactivate_last_admin_blocked(db_session, seed):
    # Actor is someone else so we get past the self-check and hit the last-admin
    # guard. `admin` is the only active administrator in the seed data.
    sales = seed["users"]["sales"]
    admin = seed["users"]["admin"]
    with pytest.raises(service.BusinessRuleError):
        service.update_user_admin(
            db_session, sales, admin.id, UserAdminUpdate(is_active=False)
        )


def test_update_move_last_admin_off_admin_role_blocked(db_session, seed):
    admin = seed["users"]["admin"]
    sales_role = seed["roles"]["sales"]
    with pytest.raises(service.BusinessRuleError):
        service.update_user_admin(
            db_session, admin, admin.id, UserAdminUpdate(role_id=sales_role.id)
        )


# ---------------------------------------------------------------------------
# activate / deactivate
# ---------------------------------------------------------------------------

def test_deactivate_user_success(db_session, seed):
    admin = seed["users"]["admin"]
    sales = seed["users"]["sales"]
    updated = service.deactivate_user(db_session, admin, sales.id)
    assert updated.is_active is False


def test_deactivate_self_blocked(db_session, seed):
    admin = seed["users"]["admin"]
    with pytest.raises(service.BusinessRuleError) as exc:
        service.deactivate_user(db_session, admin, admin.id)
    assert "your own account" in str(exc.value)


def test_deactivate_last_admin_blocked(db_session, seed):
    admin = seed["users"]["admin"]
    sales = seed["users"]["sales"]
    with pytest.raises(service.BusinessRuleError) as exc:
        service.deactivate_user(db_session, sales, admin.id)
    assert "last active administrator" in str(exc.value)


def test_activate_user_success(db_session, seed):
    admin = seed["users"]["admin"]
    disabled = seed["users"]["disabled"]
    updated = service.activate_user(db_session, admin, disabled.id)
    assert updated.is_active is True


# ---------------------------------------------------------------------------
# reset_user_password
# ---------------------------------------------------------------------------

def test_reset_user_password_success(db_session, seed):
    sales = seed["users"]["sales"]
    service.reset_user_password(db_session, sales.id, "resetpass123")
    assert verify_password("resetpass123", sales.password_hash)


def test_reset_user_password_missing_user(db_session, seed):
    with pytest.raises(service.NotFoundError):
        service.reset_user_password(db_session, uuid.uuid4(), "resetpass123")


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------

def test_delete_user_success(db_session, seed):
    admin = seed["users"]["admin"]
    sales = seed["users"]["sales"]
    service.delete_user(db_session, admin, sales.id)
    with pytest.raises(service.NotFoundError):
        service.get_user_or_404(db_session, sales.id)


def test_delete_self_blocked(db_session, seed):
    admin = seed["users"]["admin"]
    with pytest.raises(service.BusinessRuleError) as exc:
        service.delete_user(db_session, admin, admin.id)
    assert "your own account" in str(exc.value)


def test_delete_last_admin_blocked(db_session, seed):
    admin = seed["users"]["admin"]
    sales = seed["users"]["sales"]
    with pytest.raises(service.BusinessRuleError) as exc:
        service.delete_user(db_session, sales, admin.id)
    assert "last active administrator" in str(exc.value)


def test_delete_missing_user_not_found(db_session, seed):
    admin = seed["users"]["admin"]
    with pytest.raises(service.NotFoundError):
        service.delete_user(db_session, admin, uuid.uuid4())


# ---------------------------------------------------------------------------
# list_users pass-through
# ---------------------------------------------------------------------------

def test_list_users_returns_rows_and_total(db_session, seed):
    rows, total = service.list_users(
        db_session,
        search=None,
        role_id=None,
        is_active=None,
        sort="created_at",
        order="desc",
        page=1,
        page_size=20,
    )
    # The seed inserts four users.
    assert total == 4
    assert len(rows) == 4
