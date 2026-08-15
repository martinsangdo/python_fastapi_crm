-- ---------------------------------------------------------------------------
-- categories.sql  —  Categories module migration
-- ---------------------------------------------------------------------------
-- Documents the `categories` table (product categories) and seeds the
-- `categories.*` permissions — the only piece of RBAC that sql/rbac.sql did
-- NOT already seed for this module (unlike customers/products/orders, whose
-- permission codes were pre-seeded in sql/rbac.sql before their modules
-- existed).
--
-- Safe to run directly in the Supabase SQL editor, and safe to run more than
-- once: every step uses IF NOT EXISTS / ON CONFLICT so re-running it will not
-- create duplicates or error out.
--
-- NOTE: app.py already calls Base.metadata.create_all(...) on startup, but
-- that only CREATES tables that do not exist yet — since `categories`
-- already exists, create_all is a no-op for it. The CREATE TABLE below is
-- documentation of the shape the Category model in models.py expects.
-- ---------------------------------------------------------------------------

BEGIN;

-- ===========================================================================
-- 1. categories  —  product categories
-- ===========================================================================
CREATE TABLE IF NOT EXISTS categories (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    -- URL-friendly unique identifier, e.g. "home-kitchen".
    slug        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ===========================================================================
-- 2. Seed permissions — categories.read / create / update / delete
-- ===========================================================================
INSERT INTO permissions (module, action, code, description) VALUES
    ('categories', 'read',   'categories.read',   'View categories'),
    ('categories', 'create', 'categories.create', 'Create categories'),
    ('categories', 'update', 'categories.update', 'Update categories'),
    ('categories', 'delete', 'categories.delete', 'Delete categories')
ON CONFLICT (code) DO NOTHING;


-- ===========================================================================
-- 3. Grant to roles — same shape as the products.* grants in sql/rbac.sql:
--    ADMIN and MANAGER get full control, SALES gets read-only.
-- ===========================================================================

-- ADMIN already gets every permission via the CROSS JOIN in sql/rbac.sql's
-- seed step, which runs against whatever rows exist in `permissions` at the
-- time it runs. Since categories.* did not exist yet back then, ADMIN needs
-- the same catch-all grant repeated here for the new codes.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE r.code = 'ADMIN' AND p.module = 'categories'
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p
    ON p.code IN (
        'categories.read', 'categories.create',
        'categories.update', 'categories.delete'
    )
WHERE r.code = 'MANAGER'
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p
    ON p.code = 'categories.read'
WHERE r.code = 'SALES'
ON CONFLICT (role_id, permission_id) DO NOTHING;

COMMIT;
