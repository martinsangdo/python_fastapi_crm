-- ---------------------------------------------------------------------------
-- products.sql  —  Products module migration
-- ---------------------------------------------------------------------------
-- Documents the `products` table (the catalog). `products.*` permissions are
-- already seeded by sql/rbac.sql, so this file only documents the table
-- shape the Product model in models.py expects.
--
-- Safe to run directly in the Supabase SQL editor, and safe to run more than
-- once: every step uses IF NOT EXISTS so re-running it will not error out.
--
-- NOTE: app.py already calls Base.metadata.create_all(...) on startup, but
-- that only CREATES tables that do not exist yet — since `products` already
-- exists, create_all is a no-op for it.
-- ---------------------------------------------------------------------------

BEGIN;

-- ===========================================================================
-- 1. products  —  the catalog. Every product belongs to one category.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS products (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- A category with products cannot be deleted (RESTRICT).
    category_id     BIGINT NOT NULL REFERENCES categories (id) ON DELETE RESTRICT,

    sku             TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    description     TEXT NULL,

    -- Money is NUMERIC, never float — no floating-point rounding surprises.
    price           NUMERIC(12, 2) NOT NULL,

    stock_quantity  INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
