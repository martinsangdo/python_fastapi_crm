-- ---------------------------------------------------------------------------
-- customers.sql  —  Customers module migration
-- ---------------------------------------------------------------------------
-- Documents the `customers` table: the CRM's directory of people who buy
-- from us, that the Orders module builds on.
--
-- NOTE ON THE TABLE NAME: this table already existed in this Supabase
-- project (with real seeded rows) before the Customers module's Python code
-- was pointed at it. An earlier version of this module created its own
-- `crm_customers` table instead, to avoid what looked like a name collision
-- with an unrelated table — that turned out to be unnecessary: `customers`
-- IS this app's table, so the module was rewritten to use it directly.
-- `crm_customers` is no longer used by the app; it is left in place (empty)
-- rather than dropped, since dropping tables is not something a migration
-- file should do silently.
--
-- Safe to run directly in the Supabase SQL editor, and safe to run more than
-- once: every step uses IF NOT EXISTS so re-running it will not error out.
--
-- NOTE: app.py already calls Base.metadata.create_all(...) on startup, but
-- that only CREATES tables that do not exist yet — since `customers` already
-- exists, create_all is a no-op for it. This file exists purely as
-- documentation of the table shape the Customer model in models.py expects.
-- ---------------------------------------------------------------------------

BEGIN;

-- ===========================================================================
-- 1. customers  —  people who buy from us
-- ===========================================================================
CREATE TABLE IF NOT EXISTS customers (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Primary contact email. UNIQUE — one customer record per email address.
    email       TEXT NOT NULL UNIQUE,
    full_name   TEXT NOT NULL,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
