"""
navigation.py
-------------
Turns a user's PERMISSIONS into the navigation menu the frontend should show.

Per docs/rbac_guidelines.md §4 ("How frontend menus map to permissions"), a menu
item is visible only when the logged-in user holds that module's entry
permission. This module keeps the menu *metadata* (title, route, icon) in one
place and filters it against the permission codes the database says the user has.

IMPORTANT — this is NOT a permission registry and NOT a source of truth. The
permissions themselves live in the database (the single source of truth). Here we
only record, for each menu item, the permission `code` it REQUIRES, then hide the
items the user has not been granted. If a required permission does not exist in
the database, no user can ever hold it, so that menu item simply never appears
("fail closed"). Following the module.action naming convention (guidelines §3).
"""

from typing import Iterable


# The full menu, in display order. `required_permission` is the code (see the
# `permissions` table) a user must hold for the item to appear.
NAVIGATION_ITEMS: list[dict] = [
    {
        "module": "dashboard",
        "menu_title": "Dashboard",
        "route": "/dashboard",
        "icon": "dashboard",
        "required_permission": "dashboard.view",
    },
    {
        "module": "customers",
        "menu_title": "Customers",
        "route": "/customers",
        "icon": "customers",
        "required_permission": "customers.read",
    },
    {
        "module": "products",
        "menu_title": "Products",
        "route": "/products",
        "icon": "products",
        "required_permission": "products.read",
    },
    {
        "module": "orders",
        "menu_title": "Orders",
        "route": "/orders",
        "icon": "orders",
        "required_permission": "orders.read",
    },
    {
        "module": "reports",
        "menu_title": "Reports",
        "route": "/reports",
        "icon": "reports",
        "required_permission": "reports.view",
    },
    {
        "module": "users",
        "menu_title": "Users",
        "route": "/users",
        "icon": "users",
        "required_permission": "users.read",
    },
    {
        "module": "roles",
        "menu_title": "Roles",
        "route": "/roles",
        "icon": "roles",
        "required_permission": "roles.read",
    },
    {
        "module": "settings",
        "menu_title": "Settings",
        "route": "/settings",
        "icon": "settings",
        "required_permission": "settings.view",
    },
]


def build_navigation(permission_codes: Iterable[str]) -> list[dict]:
    """
    Return only the menu items whose required permission the user actually holds.

    `permission_codes` is the set of codes loaded from the database for this
    user (via authorization.get_user_permission_codes). A user therefore never
    receives a menu item for a module they cannot access.
    """
    granted = set(permission_codes)
    return [
        item
        for item in NAVIGATION_ITEMS
        if item["required_permission"] in granted
    ]
