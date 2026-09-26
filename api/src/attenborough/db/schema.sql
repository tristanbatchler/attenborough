-- The complete schema. The app applies it only through db/schema.py:reset_schema, which drops the
-- existing schema and applies this file in one transaction, then records this file's SHA-256 in
-- schema_fingerprint. At startup the app compares that hash with this file and offers a reset if
-- they differ. Run the reset from scripts/reset_db.py or answer the startup prompt. It deletes all
-- data; there are no migrations (see api/README.md, "Database").
--
-- Keep it plain DDL. No DO $$ blocks: sqlc doesn't execute them, so types created inside are
-- invisible to it and generated enums become typing.Any. IF NOT EXISTS only where a brand-new
-- schema can already have the object (extensions).

-- Extensions (a new database may inherit these from its template)
CREATE EXTENSION IF NOT EXISTS "citext";

-- Enum types
CREATE TYPE decoy_type AS ENUM ('text', 'binary', 'trap');
CREATE TYPE audit_action AS ENUM ('login', 'ban_created', 'ban_revoked', 'decoy_revoked', 'settings_changed');

------------------------------------------------------------------
-- 1. AUTHENTICATION & USERS
------------------------------------------------------------------

CREATE TABLE users (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    google_sub  TEXT NOT NULL UNIQUE,
    email       CITEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL, 
    created     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_admin    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE sessions (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires    TIMESTAMPTZ NOT NULL,
    last_used  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_sessions_expiry CHECK (expires > created)
);

CREATE INDEX idx_sessions_user_id ON sessions (user_id);
CREATE INDEX idx_sessions_expires ON sessions (expires);

CREATE TABLE oauth_states (
    state         TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    created       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires       TIMESTAMPTZ NOT NULL,
    ip_address    INET NOT NULL,

    CONSTRAINT chk_oauth_states_expiry CHECK (expires > created)
);

CREATE INDEX idx_oauth_states_expires ON oauth_states (expires);

------------------------------------------------------------------
-- 2. DECOYS & EXHIBIT ARTIFACTS
------------------------------------------------------------------

CREATE TABLE decoys (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type             decoy_type NOT NULL DEFAULT 'text',
    slug             TEXT NOT NULL,
    added            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    added_by_ip      INET NOT NULL,
    added_by_user_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    
    CONSTRAINT uq_decoys_slug UNIQUE (slug)
);

CREATE INDEX idx_decoys_added ON decoys (added DESC);

CREATE TABLE decoy_text_contents (
    decoy_id BIGINT PRIMARY KEY REFERENCES decoys (id) ON DELETE CASCADE,
    content  TEXT NOT NULL
);

CREATE TABLE decoy_binary_paths (
    decoy_id  BIGINT PRIMARY KEY REFERENCES decoys (id) ON DELETE CASCADE,
    file_path TEXT NOT NULL
);

CREATE TABLE decoy_configs (
    decoy_id      BIGINT PRIMARY KEY REFERENCES decoys (id) ON DELETE CASCADE,
    expires_at    TIMESTAMPTZ,
    password_hash TEXT,
    one_time_view BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_decoy_configs_expiry ON decoy_configs (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE decoy_revocations (
    decoy_id           BIGINT PRIMARY KEY REFERENCES decoys (id) ON DELETE RESTRICT,
    revoked_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_by_user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE RESTRICT
);

------------------------------------------------------------------
-- 3. COMPREHENSIVE HONEYPOT & TELEMETRY LOGGING
------------------------------------------------------------------

-- Every HTTP request received: served by the API itself, or by the decoy app and reported to it.
-- The request line is kept exactly as sent (one character per byte), never decoded or normalised:
-- `/cgi-bin/.%2e/.%2e/etc/passwd` is the attack, `/etc/passwd` would not be.
CREATE TABLE telemetry_hits (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ip_address   INET NOT NULL,
    method       TEXT NOT NULL,
    path         TEXT NOT NULL,
    -- After the `?`, as sent; NULL when the request line had no `?`.
    query        TEXT,
    router_group TEXT NOT NULL, 
    user_agent   TEXT,
    headers      JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- The body's first bytes (the decoy app keeps 64 KiB) and its full length, so a cut-off body is
    -- visible as body_size > octet_length(body). Both NULL when the body wasn't captured: the API
    -- doesn't capture bodies for the requests it serves itself.
    body         BYTEA,
    body_size    INTEGER,
    status_code  INTEGER NOT NULL,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_telemetry_hits_body CHECK (
        (body IS NULL) = (body_size IS NULL) AND body_size >= octet_length(body)
    )
);

-- BRIN index is optimal for high-volume, append-only time-series telemetry
CREATE INDEX idx_telemetry_hits_brin ON telemetry_hits USING brin (occurred_at);
CREATE INDEX idx_telemetry_hits_ip ON telemetry_hits (ip_address, occurred_at DESC);
CREATE INDEX idx_telemetry_hits_router ON telemetry_hits (router_group, occurred_at DESC);

-- Specialized logging for credential stuffing & brute force attempts on /honeypot/admin/login or /auth
CREATE TABLE credential_stuffing_attempts (
    id BIGSERIAL PRIMARY KEY,
    ip_address INET NOT NULL,
    endpoint_path TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    was_fake_success BOOLEAN NOT NULL DEFAULT FALSE,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_credential_attempts_ip ON credential_stuffing_attempts (ip_address, attempted_at DESC);

-- Decoy specific interaction telemetry (views, downloads)
CREATE TABLE decoy_views (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decoy_id   BIGINT NOT NULL REFERENCES decoys (id) ON DELETE CASCADE,
    ip_address INET NOT NULL,
    viewed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_decoy_views_ip ON decoy_views (ip_address, viewed_at DESC);

-- Decoy password attempts and lockouts
CREATE TABLE decoy_password_attempts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decoy_id     BIGINT NOT NULL REFERENCES decoys (id) ON DELETE CASCADE,
    ip_address   INET NOT NULL,
    successful   BOOLEAN NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_decoy_pwd_attempts_ip ON decoy_password_attempts (ip_address, attempted_at DESC);

CREATE TABLE decoy_lockouts (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decoy_id   BIGINT NOT NULL REFERENCES decoys (id) ON DELETE CASCADE,
    ip_address INET NOT NULL,
    added      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires    TIMESTAMPTZ NOT NULL,

    CONSTRAINT chk_decoy_lockouts_expiry CHECK (expires > added)
);

CREATE INDEX idx_decoy_lockouts_ip ON decoy_lockouts (ip_address, expires DESC);

------------------------------------------------------------------
-- 4. SECURITY ENFORCEMENT & AUDITING
------------------------------------------------------------------

CREATE TABLE ip_bans (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ip_address         INET NOT NULL,
    added              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires            TIMESTAMPTZ,
    reason             TEXT,
    added_by_user_id   BIGINT NOT NULL REFERENCES users (id),
    revoked_at         TIMESTAMPTZ,
    revoked_by_user_id BIGINT REFERENCES users (id),
    revocation_reason  TEXT, 

    CONSTRAINT chk_ip_bans_expiry CHECK (expires IS NULL OR expires > added),
    CONSTRAINT chk_ip_bans_revocation CHECK (revoked_at IS NULL OR revoked_at >= added)
);

CREATE INDEX idx_ip_bans_active ON ip_bans (ip_address, expires) WHERE revoked_at IS NULL;

CREATE TABLE admin_audit_log (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    action     audit_action NOT NULL,
    target_ip  INET,
    details    JSONB NOT NULL DEFAULT '{}'::jsonb,
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_admin_audit_log_time ON admin_audit_log (logged_at DESC);

------------------------------------------------------------------
-- 5. SCHEMA BOOKKEEPING
------------------------------------------------------------------

-- The SHA-256 of the schema.sql this database was built from: one row, written by reset_schema.
CREATE TABLE schema_fingerprint (
    sha256     TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
