-- ---------------------------------------------------------------------------
-- orders.sql  —  Orders module migration
-- ---------------------------------------------------------------------------
-- Documents the `orders` and `order_items` tables. `orders.*` permissions
-- are already seeded by sql/rbac.sql, so this file only documents the table
-- shapes the Order / OrderItem models in models.py expect.
--
-- Safe to run directly in the Supabase SQL editor, and safe to run more than
-- once: every step uses IF NOT EXISTS so re-running it will not error out.
--
-- NOTE: app.py already calls Base.metadata.create_all(...) on startup, but
-- that only CREATES tables that do not exist yet — since `orders` and
-- `order_items` already exist, create_all is a no-op for them.
-- ---------------------------------------------------------------------------

BEGIN;

-- ===========================================================================
-- 1. orders  —  one row per sales order
-- ===========================================================================
CREATE TABLE IF NOT EXISTS orders (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- A customer with orders cannot be hard-deleted (RESTRICT).
    customer_id          BIGINT NOT NULL REFERENCES customers (id) ON DELETE RESTRICT,

    -- One of 'pending' | 'paid' | 'shipped' | 'completed' | 'cancelled'.
    -- Enforced in the service layer (see service/orders_service.py).
    status               TEXT NOT NULL DEFAULT 'pending',

    -- Kept if the address is later removed, so the order itself survives.
    shipping_address_id  BIGINT NULL REFERENCES addresses (id) ON DELETE SET NULL,

    -- Always the sum of item line totals, recomputed server-side.
    total_amount         NUMERIC(12, 2) NOT NULL DEFAULT 0,

    placed_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ===========================================================================
-- 2. order_items  —  one row per product line on an order
-- ===========================================================================
CREATE TABLE IF NOT EXISTS order_items (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Deleting an order deletes its line items too.
    order_id     BIGINT NOT NULL REFERENCES orders (id) ON DELETE CASCADE,

    -- A product referenced by an order line cannot be hard-deleted (RESTRICT).
    product_id   BIGINT NOT NULL REFERENCES products (id) ON DELETE RESTRICT,

    quantity     INTEGER NOT NULL,

    -- Snapshot of the product's price AT ORDER TIME — later catalog price
    -- changes never rewrite the history of an already-placed order.
    unit_price   NUMERIC(12, 2) NOT NULL,

    -- The same product cannot appear twice on the same order (adjust the
    -- quantity of the existing line instead).
    CONSTRAINT ux_order_items_order_product UNIQUE (order_id, product_id)
);

COMMIT;
