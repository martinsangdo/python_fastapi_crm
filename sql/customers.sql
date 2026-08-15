-- ---------------------------------------------------------------------------
-- customers.sql  —  Customers module migration
-- ---------------------------------------------------------------------------
-- Adds the `crm_customers` table: the CRM's directory of companies/contacts
-- that the Orders, Reports and Dashboard modules will build on later.
--
-- NOTE ON THE TABLE NAME: this is named "crm_customers", not "customers",
-- because this database already has an unrelated "customers" table (from a
-- different project sharing the same Supabase instance) with its own schema
-- and data. Using a distinct name avoids colliding with it.
--
-- Safe to run directly in the Supabase SQL editor, and safe to run more than
-- once: every step uses IF NOT EXISTS so re-running it will not error out.
--
-- NOTE: app.py already calls Base.metadata.create_all(...) on startup, which
-- creates this table automatically from the Customer model in models.py. This
-- file exists for documentation / manual setup parity with that model — it is
-- not required for the app to work.
-- ---------------------------------------------------------------------------

BEGIN;

-- gen_random_uuid() lives in the pgcrypto extension. (Supabase enables this
-- already; the line is harmless if it is already on.)
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ===========================================================================
-- 1. crm_customers  —  companies / individuals the CRM tracks
-- ===========================================================================
CREATE TABLE IF NOT EXISTS crm_customers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Company or full contact name. The one field every customer must have.
    name          VARCHAR(255) NOT NULL,

    -- Contact details. All optional — a lead may start with just a name.
    email         VARCHAR(255) NULL,
    phone         VARCHAR(50)  NULL,
    company       VARCHAR(255) NULL,

    -- One of 'active' | 'inactive' | 'lead'. Enforced by the CHECK constraint
    -- below AND re-checked in the service layer (belt and suspenders).
    status        VARCHAR(20)  NOT NULL DEFAULT 'active',

    address_line  VARCHAR(255) NULL,
    city          VARCHAR(120) NULL,
    country       VARCHAR(120) NULL,
    notes         TEXT NULL,

    -- The salesperson responsible for this customer. NULL if unassigned.
    owner_id      UUID NULL REFERENCES users (id) ON DELETE SET NULL,

    -- Who created this record, for auditing.
    created_by    UUID NULL REFERENCES users (id) ON DELETE SET NULL,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_crm_customers_status
        CHECK (status IN ('active', 'inactive', 'lead'))
);

-- Helpful indexes for the list page's search/filter/sort options.
CREATE INDEX IF NOT EXISTS ix_crm_customers_name       ON crm_customers (name);
CREATE INDEX IF NOT EXISTS ix_crm_customers_status     ON crm_customers (status);
CREATE INDEX IF NOT EXISTS ix_crm_customers_owner      ON crm_customers (owner_id);
CREATE INDEX IF NOT EXISTS ix_crm_customers_created_at ON crm_customers (created_at);

COMMIT;
