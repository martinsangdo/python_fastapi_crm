# RBAC Developer Guidelines

> **The database is always the source of truth.**
>
> This document is *developer documentation only*. It explains how to **use** the
> RBAC tables that already exist — it does **not** define roles, permissions, or
> their assignments. Roles and permissions live in the database and are read from
> it at runtime. Never hardcode a role or a permission list anywhere in the
> application, and never treat this file as the authoritative list of what exists.
> When this document and the database disagree, the database wins and this
> document is out of date.

---

## 1. Overview of the RBAC architecture

RBAC (Role-Based Access Control) answers one question for every request:

> *"Is this user allowed to do this?"*

It does **not** grant permissions to users directly. Instead it follows a chain:

```
user  ->  role  ->  permissions  ->  permission.code
```

1. A **user** is assigned exactly one **role** (or none yet).
2. A **role** is granted many **permissions** through the `role_permissions`
   link table.
3. Each **permission** has a stable string `code` such as `users.read`.
4. A request that requires `users.read` is allowed only if that code appears
   among the permissions the user's role grants.

This gives a clean separation of concerns:

- **Authentication** (`dependencies.get_current_user`) proves *who* the caller
  is from their token.
- **Authorization** (`authorization.require_permission`) proves *what* the
  caller may do, by walking the chain above.

Because permissions attach to roles (not users), changing what a role can do is
a **data change** — add or remove rows in `role_permissions` — never a code
change. New roles, new permissions, and new grants are all created by writing
rows to these tables. The application code only *reads* them.

The two helper functions that implement the entire model live in
[`authorization.py`](../authorization.py):

- `get_user_permission_codes(db, user)` → returns the `set[str]` of codes the
  user has via their role (empty set if the user has no role).
- `require_permission(code)` → a FastAPI dependency factory that returns `403`
  unless the caller's role grants `code`.

Every module in the system — present and future — reuses these two functions.

---

## 2. The tables

The RBAC model is four tables (see [`models.py`](../models.py)). Column names
below are the real database columns; treat them as authoritative pointers into
the schema, not as a substitute for reading it.

### `users`

One row = one person who can log in.

| Column | Purpose |
| --- | --- |
| `id` (UUID, PK) | Unguessable identifier. |
| `email` (unique) | Login identity. |
| `password_hash` | BCrypt hash. The plaintext password is never stored. |
| `full_name` | Display name shown in the UI. |
| `is_active` (bool) | Off-switch. An inactive user cannot log in; the account is kept, not deleted. |
| `created_at` / `updated_at` / `last_login` | Audit timestamps. |
| `role_id` (FK → `roles.id`, nullable) | The user's single role. `NULL` = no role yet = **no permissions**. `ON DELETE SET NULL` — deleting a role un-assigns its users rather than deleting them. |

A user's permissions are **never** stored on the user row. They are always
derived from `role_id` at request time.

### `roles`

One row = one named group (e.g. Administrator, Manager, Sales).

| Column | Purpose |
| --- | --- |
| `id` (UUID, PK) | Identifier referenced by `users.role_id` and `role_permissions.role_id`. |
| `code` (unique) | Machine-friendly identifier (e.g. `ADMIN`). Stable; used when looking a role up in seed/admin logic. |
| `name` (unique) | Human-friendly label shown in the UI. |
| `description` | Optional explanation. |
| `is_system` (bool) | `TRUE` for built-in roles that must not be user-deleted; `FALSE` for custom roles. |
| `created_at` / `updated_at` | Audit timestamps. |

> The set of roles is **data**. Do not enumerate role codes in application logic
> (no `if role == "ADMIN"`). Authorize on *permissions*, not on role names — see
> §7.

### `permissions`

One row = one thing that can be done.

| Column | Purpose |
| --- | --- |
| `id` (UUID, PK) | Identifier referenced by `role_permissions.permission_id`. |
| `module` | Feature area (e.g. `users`, `customers`, `orders`). |
| `action` | Operation (e.g. `read`, `create`, `update`, `delete`, `view`). |
| `code` (unique) | The full `module.action` string (e.g. `users.read`). **This is the value the application checks.** |
| `description` | Optional human explanation. |
| `created_at` | Audit timestamp. |

`code` is redundant with `module` + `action` on purpose: `module`/`action` make
the catalog easy to browse and group in an admin UI, while `code` is the single
canonical string the code compares against.

### `role_permissions`

The many-to-many link table. One row = "this role has this permission."

| Column | Purpose |
| --- | --- |
| `role_id` (FK → `roles.id`, `ON DELETE CASCADE`) | Part of the composite PK. |
| `permission_id` (FK → `permissions.id`, `ON DELETE CASCADE`) | Part of the composite PK. |

The pair `(role_id, permission_id)` is the primary key, so the same permission
cannot be attached to the same role twice. Cascading deletes keep the table
clean when a role or permission is removed.

**This table is where authorization is actually configured.** Granting or
revoking a capability = inserting or deleting a row here. No code deploy is
required.

---

## 3. Permission naming conventions

Every permission `code` is exactly:

```
<module>.<action>
```

- **`module`** — lowercase, singular-or-plural but consistent per feature area,
  matching the `permissions.module` column (e.g. `users`, `customers`,
  `products`, `orders`, `reports`, `dashboard`).
- **`action`** — lowercase verb describing the operation.

Standard actions, used consistently across modules:

| Action | Meaning |
| --- | --- |
| `read` | List and view records in the module. |
| `create` | Create a new record. |
| `update` | Edit an existing record (includes state changes like activate/deactivate/reset). |
| `delete` | Remove a record. |
| `view` | See a read-only surface that isn't a CRUD list (e.g. `dashboard.view`, `reports.view`). |

Rules:

1. **One dot, two parts.** `module.action`. No nesting beyond that.
2. **Lowercase, no spaces.** Use the same casing everywhere so string compares
   are exact.
3. **Reuse the standard actions** above before inventing a new one. A genuinely
   new capability (e.g. `orders.refund`) is fine — but name it for the
   *capability*, not the button or screen that happens to trigger it.
4. **Keep codes stable.** Renaming a code silently revokes access for every role
   that had it. Treat a code as a permanent identifier once shipped.

The value your code passes to `require_permission("...")` must always be an
exact `code` string that exists in the `permissions` table.

---

## 4. How frontend menus map to permissions

A navigation menu item is a shortcut into a module. Each item is gated by that
module's **read/view** permission — the minimum needed to open the module at
all.

- Show the "Users" menu item only if the user has `users.read`.
- Show the "Reports" menu item only if the user has `reports.view`.
- A user with no matching permission should not see the menu entry at all
  (hide, don't just disable).

The frontend learns the current user's codes from
`GET /api/me/permissions` (see [`routers/users.py`](../routers/users.py)), which
returns the sorted list of codes for the logged-in user. Build the menu by
checking membership:

```js
// permissions = the array returned by GET /api/me/permissions
if (permissions.includes("users.read")) showMenu("Users");
if (permissions.includes("reports.view")) showMenu("Reports");
```

> Menu visibility is **convenience only**. Hiding a menu item does not protect
> anything — the server still enforces the permission on every request (§7).

### 4a. The `navigation` object (implementation note)

So the frontend does not have to hardcode the menu, the backend builds it and
returns it ready-filtered. `POST /auth/login` and `GET /auth/me` include a
`navigation` array; each item is:

```json
{
  "module": "customers",
  "menu_title": "Customers",
  "route": "/customers",
  "icon": "customers",
  "required_permission": "customers.read"
}
```

Rules that keep this consistent with the design above:

- The array contains **only** items whose `required_permission` is in the user's
  live permission set — a user never receives a menu item for a module they
  cannot access.
- The menu *metadata* (title, route, icon, and which permission each item
  requires) lives in [`navigation.py`](../navigation.py). That file is **not** a
  permission registry and **not** a source of truth: it only maps a menu item to
  the permission `code` it needs. The permissions themselves, and who has them,
  remain in the database.
- If a listed item's `required_permission` does not exist in the `permissions`
  table, no user can hold it, so the item simply never appears ("fail closed").

The frontend builds its sidebar directly from this array and still uses the flat
`permissions` list (§6) to show/hide individual buttons.

---

## 5. How pages map to permissions

A page (route/view) belongs to a module and requires that module's entry
permission to render:

| Page | Required permission |
| --- | --- |
| Users list / detail | `users.read` |
| Customers list / detail | `customers.read` |
| Reports page | `reports.view` |
| Dashboard | `dashboard.view` |

Guidance:

- Gate the page on the **least** permission it needs to be useful — usually the
  `read`/`view` code. A user who can read a page but not edit it still sees the
  page, just with write actions hidden (§6).
- If a user reaches a page they lack permission for (typed the URL, stale link),
  redirect them away or show a "not authorized" state. The backend API calls the
  page makes will already return `403`, so the page must degrade gracefully.
- Never rely on the page being hidden as the security boundary — the boundary is
  the API (§7).

---

## 6. How buttons map to permissions

A button represents a single action, so it maps to the **specific** permission
that action needs — usually a write permission:

| Button | Required permission |
| --- | --- |
| "New user" | `users.create` |
| "Edit" / "Save" / "Reset password" / "Activate" / "Deactivate" | `users.update` |
| "Delete" | `users.delete` |

Pattern:

```js
if (permissions.includes("users.create")) enable("New user button");
if (permissions.includes("users.delete")) enable("Delete button");
```

- Hide or disable a button when the user lacks its permission. Hiding is usually
  clearer than disabling.
- The permission a button checks on the client must be the **same code** the
  backend endpoint enforces for that action, so the UI and the API never
  disagree. (E.g. the "Reset password" button checks `users.update` because
  `POST /api/users/{id}/reset-password` requires `users.update`.)
- Client-side button gating is UX, not security. A user who forces the request
  anyway is still stopped by the server.

---

## 7. Backend API authorization

The backend is the **only** real security boundary. Menus, pages, and buttons
are hints; the API enforces.

Every protected endpoint declares the permission it needs with the
`require_permission` dependency from [`authorization.py`](../authorization.py):

```python
from authorization import require_permission
from models import User

@router.get("/api/users", response_model=UserListPage)
def list_users(
    _: User = Depends(require_permission("users.read")),
    db: Session = Depends(get_db),
):
    ...
```

How it works:

1. `require_permission("users.read")` returns a dependency.
2. That dependency first runs `get_current_user` (authentication). An invalid or
   missing token → `401`.
3. It then computes `get_user_permission_codes(db, user)` — the user's role's
   permission codes — and checks whether `"users.read"` is in that set.
4. Not present → `HTTP 403 Forbidden`. Present → the request proceeds, and the
   dependency hands back the fully-loaded `User`, so the route both authorizes
   and knows who is calling.

Conventions for module authors:

- **Every** state-changing or data-returning endpoint gets a
  `require_permission(...)` matching the action's code. Read endpoints use
  `.read`/`.view`; writes use `.create`/`.update`/`.delete`.
- Authorize on **permission codes**, never on role names. Do not write
  `if user.role.code == "ADMIN"`. If a capability should be admin-only, model it
  as a permission and grant that permission to the admin role in the database.
- The permission string passed here must exist in the `permissions` table. If it
  doesn't, no role can ever satisfy it and the endpoint is effectively locked to
  everyone.
- An endpoint any logged-in user may call (e.g. `GET /api/me/permissions`) uses
  plain `get_current_user` instead of `require_permission`.

---

## 8. How the login endpoint loads role and permissions

Login authenticates the user; it must resolve authorization from the database,
never from anything the client sends.

At login (`POST /auth/login`, see [`routers/auth.py`](../routers/auth.py)):

1. Verify email + `password_hash`. On failure → `401`.
2. Confirm `is_active` is true. A disabled account cannot log in.
3. Load the user **with their role**, following `users.role_id → roles`.
4. Resolve the effective permission codes via
   `get_user_permission_codes(db, user)` — this walks
   `role → role_permissions → permissions.code` and returns the set of codes.
5. Issue the token(s). The token identifies the user (its `sub` is the user id);
   it is **not** where permissions are stored.

Important rules:

- **Never** read role or permissions from the request body, a header, or the
  token payload. They are always re-derived from the database via `role_id`.
- Because permissions are re-derived on each request (§7), a permission change
  in `role_permissions` takes effect on the user's next request — there is no
  stale copy baked into the token.
- If the login response includes the user's role/permissions for the client to
  bootstrap its UI, treat that payload as a **convenience snapshot**. The
  authoritative, always-current source remains `GET /api/me/permissions` and the
  per-request server checks.

**Implementation note (as shipped).** `POST /auth/login` returns a
`LoginResponse` (see [`schemas.py`](../schemas.py)):

```json
{
  "access_token": "…",
  "refresh_token": "…",
  "token_type": "bearer",
  "user": { "id": "…", "email": "…", "full_name": "…", "is_active": true, "…": "…" },
  "role": { "id": "…", "code": "SALES", "name": "Sales" },
  "permissions": ["customers.read", "dashboard.view"],
  "navigation": [ { "module": "dashboard", "…": "…" } ]
}
```

- `role` and `permissions` are resolved from the database via
  `get_user_permission_codes` at request time; the permission set is loaded
  **once** and reused for both `permissions` and `navigation`.
- The **access token** carries only `sub` (user_id), `email`, `role_id`, and
  `exp` — never permissions. `password_hash` is never included anywhere in the
  response.
- The token/`token_type` fields are unchanged from before, so existing clients
  keep working (backward compatible).

---

## 9. How `GET /auth/me` should return role and permissions

`GET /auth/me` returns the profile of the currently authenticated user. To let
the frontend render itself correctly, its response should describe the user's
authorization as it exists **right now in the database**, freshly resolved on
each call:

- **`role`** — the user's current role from `users.role_id` (e.g. its `code`,
  `name`). `null` when the user has no role assigned.
- **`permissions`** — the array of permission `code` strings the user's role
  grants, produced by `get_user_permission_codes(db, current_user)`.

Guidance:

- Compute both values from the database on every call. Do not cache them on the
  user row or read them from the token — a role reassignment or a
  `role_permissions` change must be reflected immediately on the next
  `GET /auth/me`.
- A user with no role returns `role: null` and `permissions: []`.
- The frontend uses this response to drive menu/page/button visibility (§4–6).
  The list is identical to what `GET /api/me/permissions` returns; `/auth/me`
  simply bundles it with the profile so the app can bootstrap in one call.
- This endpoint is available to any authenticated user (guard with
  `get_current_user`, not `require_permission`).

**Implementation note (as shipped).** `GET /auth/me` returns a `MeResponse` with
`user`, `role`, `permissions`, and the same permission-filtered `navigation`
array as login (§4a) — all recomputed from the database on each call.

---

## 10. How future modules register new permissions

When a new module needs new capabilities, the capabilities are **created as data
in the `permissions` table** — not declared in code.

For each capability the module needs:

1. Decide the `code` using the §3 convention: `module.action`
   (e.g. `customers.read`, `customers.create`, `customers.update`,
   `customers.delete`).
2. Insert a row into `permissions` with matching `module`, `action`, `code`, and
   a helpful `description`. (How you insert — migration, seed script, admin
   screen — is a project decision; this document does not prescribe or generate
   SQL.)
3. Grant the new permission to the roles that should have it by inserting rows
   into `role_permissions`. A permission that exists but is granted to no role is
   inert — nobody can use the endpoints that require it.

Rules:

- The application code **references** codes (via `require_permission("...")`) but
  never **creates** them and never keeps its own list of "all permissions." The
  `permissions` table is the catalog.
- Reuse the standard actions (§3) so the new module feels consistent with
  existing ones.
- Keep new codes stable once shipped.

---

## 11. Updating the database when creating a new module

A checklist for the data side of adding a module (e.g. "Customers"). None of
these steps are code that hardcodes roles/permissions — they are database rows
that the running application reads.

1. **Add the module's permissions.** Insert one `permissions` row per capability
   (`customers.read`, `customers.create`, `customers.update`,
   `customers.delete`, and any capability-specific codes like
   `customers.export`). Fill in `module`, `action`, `code`, `description`.
2. **Grant them to roles.** Insert `role_permissions` rows connecting each new
   permission to the roles that should have it. This is the step that actually
   turns access on. Decide grants per role (e.g. an admin role gets all;
   a read-only role gets only `.read`/`.view`).
3. **Protect the endpoints.** In the module's router, guard every endpoint with
   `require_permission("<the matching code>")`. The code you pass must exactly
   equal a `code` you inserted in step 1.
4. **Expose the codes to the frontend.** No new endpoint is needed — the new
   codes automatically flow through `GET /api/me/permissions` (and `/auth/me`,
   §9) because those read the user's live permission set.
5. **Gate the UI.** Add the menu item (§4), page (§5), and buttons (§6), each
   checking its matching code from the permissions list.
6. **Verify end-to-end.** Log in as a role that was granted the new permissions
   and confirm the UI appears and the API allows the action; log in as a role
   that was **not** granted them and confirm the menu/buttons are hidden **and**
   the API returns `403`.

If a capability appears not to work, check the data first: does the `permissions`
row exist, and is there a `role_permissions` row linking it to the user's role?
Missing access is almost always a missing row, not a code bug — because the
database, not this document and not the code, is the source of truth.
