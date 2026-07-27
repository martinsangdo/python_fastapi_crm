-- ---------------------------------------------------------------------------
-- users.sql
-- ---------------------------------------------------------------------------
-- The SQL behind the authentication module's `users` table.
--
-- You normally do NOT need to run this by hand: app.py calls
-- Base.metadata.create_all(...) on startup and creates the same table for you.
-- This script is provided as documentation and for anyone who prefers to set
-- the table up directly in PostgreSQL / Supabase (e.g. the Supabase SQL editor).
-- ---------------------------------------------------------------------------

-- gen_random_uuid() lives in the pgcrypto extension. Enable it once per
-- database so the DEFAULT below works. (Supabase has this enabled already.)
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- The main table.
CREATE TABLE IF NOT EXISTS users (
    -- Primary key: a random UUID, generated automatically for each new row.
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Login email. NOT NULL + UNIQUE means every user must have one, and no
    -- two users can share it.
    email         VARCHAR(255) NOT NULL UNIQUE,

    -- The BCRYPT password hash. We never store the plain password.
    password_hash VARCHAR(255) NOT NULL,

    -- The person's display name.
    full_name     VARCHAR(255) NOT NULL,

    -- Whether the account may log in. TRUE by default.
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,

    -- Timestamps. created_at/updated_at default to "now"; last_login stays
    -- NULL until the user's first successful login.
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_login    TIMESTAMPTZ
);


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
-- The UNIQUE constraint on email already creates an index, but we add an
-- explicit named one to make the intent obvious and keep email look-ups fast.
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);


-- ---------------------------------------------------------------------------
-- Keep updated_at fresh automatically
-- ---------------------------------------------------------------------------
-- SQLAlchemy handles this in Python (onupdate=func.now()). If you INSERT or
-- UPDATE rows with raw SQL instead, this trigger keeps updated_at correct.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();


-- ---------------------------------------------------------------------------
-- Sample seed user
-- ---------------------------------------------------------------------------
-- Email:    admin@example.com
-- Password: Password123!
-- The password_hash below is a real BCRYPT hash of "Password123!", so you can
-- log in with this account immediately after seeding.
-- ON CONFLICT keeps this script safe to run more than once.
INSERT INTO users (email, password_hash, full_name)
VALUES (
    'admin@example.com',
    '$2b$12$YJWleKiNOAGJ2P..WnboVOHZV/AodAPa.4hselqWY/pBPHIupayCC',
    'CRM Administrator'
)
ON CONFLICT (email) DO NOTHING;
