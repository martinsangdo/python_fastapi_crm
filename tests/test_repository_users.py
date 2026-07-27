"""
tests/test_repository_users.py
------------------------------
REPOSITORY-LAYER tests for users_repository.py.

These verify the raw data-access helpers against the in-memory SQLite database:
filtering, sorting, paging, the safe fallback for unknown sort keys, the
last-admin counter, and the add/save/delete primitives. No business logic and no
HTTP is involved here — just the SQL surface the service layer builds on.
"""

import uuid

import users_repository as repo
from models import User
from security import hash_password


# ---------------------------------------------------------------------------
# list_users — filtering
# ---------------------------------------------------------------------------

def test_list_users_no_filters_returns_all(db_session, seed):
    rows, total = repo.list_users(db_session)
    assert total == 4
    assert len(rows) == 4


def test_list_users_search_matches_email_or_name(db_session, seed):
    rows, total = repo.list_users(db_session, search="admin")
    assert total == 1
    assert rows[0].email == "admin@example.com"

    # Search is case-insensitive and matches the full_name too.
    rows, total = repo.list_users(db_session, search="sales user")
    assert total == 1
    assert rows[0].email == "sales@example.com"


def test_list_users_filter_by_role(db_session, seed):
    sales_role = seed["roles"]["sales"]
    rows, total = repo.list_users(db_session, role_id=sales_role.id)
    # sales (active) + disabled (inactive) both hold the SALES role.
    assert total == 2
    assert {u.email for u in rows} == {"sales@example.com", "disabled@example.com"}


def test_list_users_filter_active_only(db_session, seed):
    rows, total = repo.list_users(db_session, is_active=True)
    assert total == 3
    assert all(u.is_active for u in rows)


def test_list_users_filter_inactive_only(db_session, seed):
    rows, total = repo.list_users(db_session, is_active=False)
    assert total == 1
    assert rows[0].email == "disabled@example.com"


# ---------------------------------------------------------------------------
# list_users — sorting & paging
# ---------------------------------------------------------------------------

def test_list_users_sort_by_email_ascending(db_session, seed):
    rows, _ = repo.list_users(db_session, sort="email", order="asc")
    emails = [u.email for u in rows]
    assert emails == sorted(emails)


def test_list_users_unknown_sort_falls_back_to_created_at(db_session, seed):
    # An unknown/invalid sort key must not crash — it falls back safely.
    rows, total = repo.list_users(db_session, sort="password_hash; DROP TABLE users")
    assert total == 4
    assert len(rows) == 4


def test_list_users_paging(db_session, seed):
    page1, total = repo.list_users(db_session, page=1, page_size=2)
    assert total == 4
    assert len(page1) == 2

    page2, _ = repo.list_users(db_session, page=2, page_size=2)
    assert len(page2) == 2
    # The two pages do not overlap.
    assert {u.id for u in page1}.isdisjoint({u.id for u in page2})


def test_list_users_page_size_is_clamped(db_session, seed):
    # page_size above the 100 cap is clamped; page below 1 is clamped to 1.
    rows, total = repo.list_users(db_session, page=0, page_size=9999)
    assert total == 4
    assert len(rows) == 4


# ---------------------------------------------------------------------------
# Single-row lookups
# ---------------------------------------------------------------------------

def test_get_user_found_and_missing(db_session, seed):
    admin = seed["users"]["admin"]
    assert repo.get_user(db_session, admin.id).id == admin.id
    assert repo.get_user(db_session, uuid.uuid4()) is None


def test_get_user_by_email(db_session, seed):
    assert repo.get_user_by_email(db_session, "sales@example.com").email == (
        "sales@example.com"
    )
    assert repo.get_user_by_email(db_session, "ghost@example.com") is None


def test_get_role(db_session, seed):
    sales_role = seed["roles"]["sales"]
    assert repo.get_role(db_session, sales_role.id).code == "SALES"
    assert repo.get_role(db_session, uuid.uuid4()) is None


def test_list_roles_ordered_by_name(db_session, seed):
    roles = repo.list_roles(db_session)
    names = [r.name for r in roles]
    # Ordered alphabetically: "Administrator" before "Sales".
    assert names == sorted(names)
    assert names == ["Administrator", "Sales"]


# ---------------------------------------------------------------------------
# count_active_admins
# ---------------------------------------------------------------------------

def test_count_active_admins(db_session, seed):
    # The seed has exactly one active ADMIN user.
    assert repo.count_active_admins(db_session) == 1


def test_count_active_admins_ignores_inactive(db_session, seed):
    # Deactivating the only admin drops the count to zero.
    admin = seed["users"]["admin"]
    admin.is_active = False
    db_session.commit()
    assert repo.count_active_admins(db_session) == 0


# ---------------------------------------------------------------------------
# add_user / save / delete_user
# ---------------------------------------------------------------------------

def test_add_user_persists_and_fills_defaults(db_session, seed):
    user = User(
        email="added@example.com",
        full_name="Added User",
        password_hash=hash_password("secret123"),
    )
    saved = repo.add_user(db_session, user)
    assert saved.id is not None
    assert saved.created_at is not None
    # is_active defaults to True.
    assert saved.is_active is True
    assert repo.get_user_by_email(db_session, "added@example.com") is not None


def test_save_writes_changes(db_session, seed):
    sales = seed["users"]["sales"]
    sales.full_name = "Changed Name"
    saved = repo.save(db_session, sales)
    assert saved.full_name == "Changed Name"
    # Re-reading from the database confirms the change was committed.
    assert repo.get_user(db_session, sales.id).full_name == "Changed Name"


def test_delete_user_removes_row(db_session, seed):
    sales = seed["users"]["sales"]
    repo.delete_user(db_session, sales)
    assert repo.get_user(db_session, sales.id) is None
