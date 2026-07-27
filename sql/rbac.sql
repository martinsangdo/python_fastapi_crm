-- ---------------------------------------------------------------------------
-- rbac.sql  —  Role-Based Access Control (RBAC) migration
-- ---------------------------------------------------------------------------
-- Adds roles + permissions on top of the EXISTING `users` table.
--
-- What this does, in plain terms:
--   * Every user can be given ONE role (Admin, Manager, Sales, ...).
--   * Every role owns a set of permissions (e.g. "customers.read").
--   * To check "can this user do X?", follow: user -> role -> permissions.
--
-- Safe to run directly in the Supabase SQL editor. It is also safe to run more
-- than once: every step uses IF NOT EXISTS / ON CONFLICT so re-running it will
-- not create duplicates or error out.
--
-- NOTE ON ORDER: the `roles` table is created BEFORE we add users.role_id,
-- because the foreign key on users points at roles.id and that table must
-- already exist. The existing `users` table itself is never recreated.
-- ---------------------------------------------------------------------------

-- Wrap everything in one transaction: either the whole migration applies, or
-- nothing does. You never end up half-migrated.
BEGIN;

-- gen_random_uuid() lives in the pgcrypto extension. (Supabase enables this
-- already; the line is harmless if it is already on.)
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ===========================================================================
-- 1. roles  —  the named groups a user can belong to
-- ===========================================================================
CREATE TABLE IF NOT EXISTS roles (
    -- Random UUID primary key, generated automatically for each new row.
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Machine-friendly code used in application logic, e.g. 'ADMIN'. UNIQUE so
    -- code can be looked up reliably.
    code        VARCHAR(50)  NOT NULL UNIQUE,

    -- Human-friendly display name shown in the UI, e.g. 'Administrator'.
    name        VARCHAR(100) NOT NULL UNIQUE,

    -- Optional longer explanation of what the role is for.
    description TEXT,

    -- TRUE for roles that ship with the system (and should not be deleted by
    -- users). FALSE for custom roles someone creates later.
    is_system   BOOLEAN      DEFAULT TRUE,

    -- Timestamps. Both default to "now" when the row is inserted.
    created_at  TIMESTAMPTZ  DEFAULT now(),
    updated_at  TIMESTAMPTZ  DEFAULT now()
);


-- ===========================================================================
-- 2. permissions  —  the individual things a role is allowed to do
-- ===========================================================================
-- Each permission is one "module.action" pair, e.g. module='customers',
-- action='read', code='customers.read'. The `code` is what the app checks.
CREATE TABLE IF NOT EXISTS permissions (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),

    -- The feature area, e.g. 'customers', 'orders', 'reports'.
    module      VARCHAR(100) NOT NULL,

    -- The operation, e.g. 'read', 'create', 'update', 'delete', 'view'.
    action      VARCHAR(50)  NOT NULL,

    -- The full permission string "module.action", e.g. 'customers.read'.
    -- UNIQUE so each permission exists exactly once.
    code        VARCHAR(150) NOT NULL UNIQUE,

    -- Optional description of what the permission grants.
    description TEXT,

    created_at  TIMESTAMPTZ  DEFAULT now()
);


-- ===========================================================================
-- 3. role_permissions  —  which permissions each role has (many-to-many)
-- ===========================================================================
-- A join table: one row means "this role has this permission". A role has many
-- permissions, and a permission can belong to many roles.
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       UUID NOT NULL,
    permission_id UUID NOT NULL,

    -- The pair (role_id, permission_id) is the primary key, so the same
    -- permission cannot be attached to the same role twice.
    PRIMARY KEY (role_id, permission_id),

    -- If a role is deleted, drop its permission links automatically.
    FOREIGN KEY (role_id)
        REFERENCES roles (id)
        ON DELETE CASCADE,

    -- If a permission is deleted, drop its links from every role automatically.
    FOREIGN KEY (permission_id)
        REFERENCES permissions (id)
        ON DELETE CASCADE
);

-- Helpful index for "list all roles that have permission X" style look-ups.
-- (The composite primary key already covers "permissions of a given role".)
CREATE INDEX IF NOT EXISTS ix_role_permissions_permission_id
    ON role_permissions (permission_id);


-- ===========================================================================
-- 4. users.role_id  —  link each existing user to a role
-- ===========================================================================
-- Only ADD a nullable column + foreign key + index. No existing column on the
-- users table is touched, and the table is NOT recreated.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS role_id UUID NULL;

-- Foreign key: users.role_id -> roles.id.
-- ON DELETE SET NULL: if a role is removed, affected users simply lose their
-- role (they are not deleted). Guarded so re-running does not error.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_role_id'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_role_id
            FOREIGN KEY (role_id)
            REFERENCES roles (id)
            ON DELETE SET NULL;
    END IF;
END$$;

-- Index so filtering/joining users by role stays fast.
CREATE INDEX IF NOT EXISTS ix_users_role_id ON users (role_id);


-- ===========================================================================
-- 5. Seed data
-- ===========================================================================

-- 5a. Roles ------------------------------------------------------------------
INSERT INTO roles (code, name, description) VALUES
    ('ADMIN',   'Administrator', 'Full access to every module and setting.'),
    ('MANAGER', 'Manager',       'Manages customers, products and orders; can view reports.'),
    ('SALES',   'Sales',         'Day-to-day sales work on customers and orders.')
ON CONFLICT (code) DO NOTHING;


-- 5b. Permissions ------------------------------------------------------------
-- One row per "module.action". Descriptions are auto-built from the two parts.
INSERT INTO permissions (module, action, code, description) VALUES
    ('customers', 'read',   'customers.read',   'View customers'),
    ('customers', 'create', 'customers.create', 'Create customers'),
    ('customers', 'update', 'customers.update', 'Update customers'),
    ('customers', 'delete', 'customers.delete', 'Delete customers'),

    ('products',  'read',   'products.read',    'View products'),
    ('products',  'create', 'products.create',  'Create products'),
    ('products',  'update', 'products.update',  'Update products'),
    ('products',  'delete', 'products.delete',  'Delete products'),

    ('orders',    'read',   'orders.read',      'View orders'),
    ('orders',    'create', 'orders.create',    'Create orders'),
    ('orders',    'update', 'orders.update',    'Update orders'),
    ('orders',    'delete', 'orders.delete',    'Delete orders'),

    ('users',     'read',   'users.read',       'View users'),
    ('users',     'create', 'users.create',     'Create users'),
    ('users',     'update', 'users.update',     'Update users'),
    ('users',     'delete', 'users.delete',     'Delete users'),

    ('reports',   'view',   'reports.view',     'View reports'),
    ('settings',  'manage', 'settings.manage',  'Manage system settings')
ON CONFLICT (code) DO NOTHING;


-- 5c. Assign permissions to roles -------------------------------------------
-- We insert into role_permissions by SELECTing the matching role + permission
-- rows, so we never have to hard-code UUIDs. ON CONFLICT keeps it idempotent.

-- ADMIN: gets EVERY permission (CROSS JOIN pairs the admin role with all rows).
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.code = 'ADMIN'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- MANAGER: full control of customers / products / orders, plus reports.
-- No user administration, no settings.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p
    ON p.code IN (
        'customers.read', 'customers.create', 'customers.update', 'customers.delete',
        'products.read',  'products.create',  'products.update',  'products.delete',
        'orders.read',    'orders.create',    'orders.update',    'orders.delete',
        'reports.view'
    )
WHERE r.code = 'MANAGER'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- SALES: work with customers and orders, read products, view reports.
-- No deletes, no product/user/settings management.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p
    ON p.code IN (
        'customers.read', 'customers.create', 'customers.update',
        'products.read',
        'orders.read',    'orders.create',    'orders.update',
        'reports.view'
    )
WHERE r.code = 'SALES'
ON CONFLICT (role_id, permission_id) DO NOTHING;


COMMIT;
