"""
authorization.py
----------------
The RBAC (Role-Based Access Control) "gate" for the API.

Authentication (dependencies.get_current_user) answers *"who are you?"*.
Authorization answers the next question: *"are you allowed to do this?"*.

To decide that, we follow the chain the RBAC tables describe:

    user  ->  role  ->  permissions  ->  permission.code

If the permission the route needs (e.g. "users.read") is among the codes the
user's role grants, the request is allowed through. Otherwise we stop it with a
403 ("Forbidden") response.

This file is deliberately small and reusable: EVERY future module (Customers,
Products, Orders, ...) protects its routes with `require_permission(...)`.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import User


def get_user_permission_codes(db: Session, user: User) -> set[str]:
    """
    Return the set of permission codes a user has, via their role.

    - A user with no role has NO permissions (an empty set).
    - Otherwise we collect every `code` (e.g. "users.read") attached to the
      user's role through the role_permissions link table.

    We return a `set` so membership checks ("is this code allowed?") are fast
    and so duplicates cannot creep in.
    """
    # `db` is accepted for symmetry with the rest of the codebase and in case a
    # future version needs to re-query; here SQLAlchemy's relationships already
    # give us everything we need by walking user -> role -> permissions.
    if user.role is None:
        return set()
    return {permission.code for permission in user.role.permissions}


def require_permission(code: str):
    """
    Build a FastAPI dependency that only lets a request through if the logged-in
    user's role grants the given permission `code`.

    Usage inside a router:

        @router.get("/api/users")
        def list_users(user: User = Depends(require_permission("users.read"))):
            ...

    The returned `user` is the fully-loaded, authenticated User object, so a
    route can both authorize AND know who is calling in a single dependency.
    """

    def _checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        # get_current_user already proved the token is valid and the account is
        # active. Now we only need to check the permission.
        if code not in get_user_permission_codes(db, user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have permission to perform this action ({code}).",
            )
        return user

    return _checker
