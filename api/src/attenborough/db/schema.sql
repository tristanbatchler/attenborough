-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "citext";

CREATE TYPE decoy_type AS ENUM ('text', 'binary', 'trap');
CREATE TYPE audit_action AS ENUM ('login', 'ban_created', 'ban_revoked', 'decoy_revoked', 'settings_changed');

------------------------------------------------------------------
-- 1. AUTHENTICATION & USERS
------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    google_sub  TEXT NOT NULL UNIQUE,
    email       CITEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL, 
    created     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_admin    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS sessions (
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

CREATE TABLE IF NOT EXISTS oauth_states (
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

CREATE TABLE IF NOT EXISTS decoys (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type             decoy_type NOT NULL DEFAULT 'text',
    slug             TEXT NOT NULL,
    added            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    added_by_ip      INET NOT NULL,
    added_by_user_id BIGINT REFERENCES users (id) ON DELETE SET NULL,
    
    CONSTRAINT uq_decoys_slug UNIQUE (slug)
);

CREATE INDEX idx_decoys_added ON decoys (added DESC);

CREATE TABLE IF NOT EXISTS decoy_text_contents (
    decoy_id BIGINT PRIMARY KEY REFERENCES decoys (id) ON DELETE CASCADE,
    content  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decoy_binary_paths (
    decoy_id  BIGINT PRIMARY KEY REFERENCES decoys (id) ON DELETE CASCADE,
    file_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decoy_configs (
    decoy_id      BIGINT PRIMARY KEY REFERENCES decoys (id) ON DELETE CASCADE,
    expires_at    TIMESTAMPTZ,
    password_hash TEXT,
    one_time_view BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_decoy_configs_expiry ON decoy_configs (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS decoy_revocations (
    decoy_id           BIGINT PRIMARY KEY REFERENCES decoys (id) ON DELETE RESTRICT,
    revoked_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_by_user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE RESTRICT
);

------------------------------------------------------------------
-- 3. COMPREHENSIVE HONEYPOT & TELEMETRY LOGGING
------------------------------------------------------------------

-- Raw HTTP requests hitting any endpoint (Exhibit or Honeypot routers: admin, auth, backup, etc.)
CREATE TABLE IF NOT EXISTS telemetry_hits (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ip_address   INET NOT NULL,
    method       TEXT NOT NULL,
    path         TEXT NOT NULL,
    router_group TEXT NOT NULL, -- e.g., 'admin', 'git', 'backup', 'exhibit'
    user_agent   TEXT,
    headers      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status_code  INTEGER NOT NULL,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- BRIN index is optimal for high-volume, append-only time-series telemetry
CREATE INDEX idx_telemetry_hits_brin ON telemetry_hits USING brin (occurred_at);
CREATE INDEX idx_telemetry_hits_ip ON telemetry_hits (ip_address, occurred_at DESC);
CREATE INDEX idx_telemetry_hits_router ON telemetry_hits (router_group, occurred_at DESC);

-- Specialized logging for credential stuffing & brute force attempts on /honeypot/admin/login or /auth
CREATE TABLE IF NOT EXISTS credential_stuffing_attempts (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ip_address    INET NOT NULL,
    endpoint_path TEXT NOT NULL,
    username      TEXT NOT NULL,
    password      TEXT NOT NULL,
    attempted_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_credential_attempts_ip ON credential_stuffing_attempts (ip_address, attempted_at DESC);

-- Decoy specific interaction telemetry (views, downloads)
CREATE TABLE IF NOT EXISTS decoy_views (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decoy_id   BIGINT NOT NULL REFERENCES decoys (id) ON DELETE CASCADE,
    ip_address INET NOT NULL,
    viewed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_decoy_views_ip ON decoy_views (ip_address, viewed_at DESC);

-- Decoy password attempts and lockouts
CREATE TABLE IF NOT EXISTS decoy_password_attempts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decoy_id     BIGINT NOT NULL REFERENCES decoys (id) ON DELETE CASCADE,
    ip_address   INET NOT NULL,
    successful   BOOLEAN NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_decoy_pwd_attempts_ip ON decoy_password_attempts (ip_address, attempted_at DESC);

CREATE TABLE IF NOT EXISTS decoy_lockouts (
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

CREATE TABLE IF NOT EXISTS ip_bans (
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

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    action     audit_action NOT NULL,
    target_ip  INET,
    details    JSONB NOT NULL DEFAULT '{}'::jsonb,
    logged_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_admin_audit_log_time ON admin_audit_log (logged_at DESC);