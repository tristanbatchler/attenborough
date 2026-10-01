-- The schema the honeypot went live with (2026-10). Every later change is a new migration.

-- Extensions (a new database may inherit these from its template)
CREATE EXTENSION IF NOT EXISTS "citext";

-- Enum types
CREATE TYPE decoy_type AS ENUM ('text', 'binary', 'trap');
CREATE TYPE audit_action AS ENUM ('login', 'ban_created', 'ban_revoked', 'decoy_revoked', 'settings_changed');
-- What a request was for, recorded with each hit; a router's tags carry its group (sqlc generates
-- the RouterGroup enum the API uses). 'ingest' is the decoy app reporting its visitors' requests:
-- records, not visits, so it is never stored.
CREATE TYPE router_group AS ENUM ('exhibit', 'system', 'honeypot', 'ingest');
-- The kinds of event the exhibit lists (queries.sql, ListRecentEvents).
CREATE TYPE event_kind AS ENUM ('hit', 'login_attempt', 'decoy_view', 'decoy_password_attempt');

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
    router_group router_group NOT NULL,
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
-- The exhibit's listings page through events newest first, by (time, id): see ListRecentEvents.
CREATE INDEX idx_telemetry_hits_ip ON telemetry_hits (ip_address, occurred_at DESC, id DESC);
CREATE INDEX idx_telemetry_hits_router ON telemetry_hits (router_group, occurred_at DESC, id DESC);

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

CREATE INDEX idx_credential_attempts_ip ON credential_stuffing_attempts (ip_address, attempted_at DESC, id DESC);
CREATE INDEX idx_credential_attempts_time ON credential_stuffing_attempts (attempted_at DESC, id DESC);

-- Decoy specific interaction telemetry (views, downloads)
CREATE TABLE decoy_views (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decoy_id   BIGINT NOT NULL REFERENCES decoys (id) ON DELETE CASCADE,
    ip_address INET NOT NULL,
    viewed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_decoy_views_ip ON decoy_views (ip_address, viewed_at DESC, id DESC);
CREATE INDEX idx_decoy_views_time ON decoy_views (viewed_at DESC, id DESC);

-- Decoy password attempts and lockouts
CREATE TABLE decoy_password_attempts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decoy_id     BIGINT NOT NULL REFERENCES decoys (id) ON DELETE CASCADE,
    ip_address   INET NOT NULL,
    successful   BOOLEAN NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_decoy_pwd_attempts_ip ON decoy_password_attempts (ip_address, attempted_at DESC, id DESC);
CREATE INDEX idx_decoy_pwd_attempts_time ON decoy_password_attempts (attempted_at DESC, id DESC);

CREATE TABLE decoy_lockouts (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decoy_id   BIGINT NOT NULL REFERENCES decoys (id) ON DELETE CASCADE,
    ip_address INET NOT NULL,
    added      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires    TIMESTAMPTZ NOT NULL,

    CONSTRAINT chk_decoy_lockouts_expiry CHECK (expires > added)
);

CREATE INDEX idx_decoy_lockouts_ip ON decoy_lockouts (ip_address, expires DESC);

-- Running totals per address, for the exhibit's summary of one IP: counting a busy scanner's
-- million rows on every page view would take seconds. Kept by the insert triggers below, so every
-- way a row is inserted keeps them right. Nothing deletes events; anything that ever does must
-- recompute these.
CREATE TABLE ip_activity (
    ip_address     INET PRIMARY KEY,
    -- Honeypot requests only, as the exhibit lists them.
    requests       BIGINT NOT NULL DEFAULT 0,
    distinct_paths BIGINT NOT NULL DEFAULT 0,
    login_attempts BIGINT NOT NULL DEFAULT 0,
    -- The first and last honeypot request; NULL while there are none.
    first_seen_at  TIMESTAMPTZ,
    last_seen_at   TIMESTAMPTZ
);

-- Each path an address requested, once, by the MD5 of the path as sent: paths can be longer than
-- a btree entry may be.
CREATE TABLE ip_request_paths (
    ip_address INET NOT NULL,
    path_md5   UUID NOT NULL,

    PRIMARY KEY (ip_address, path_md5)
);

CREATE FUNCTION count_ip_request() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    new_paths INTEGER;
BEGIN
    INSERT INTO ip_request_paths (ip_address, path_md5)
    VALUES (NEW.ip_address, md5(NEW.path)::uuid)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS new_paths = ROW_COUNT;
    INSERT INTO ip_activity AS a (ip_address, requests, distinct_paths, first_seen_at, last_seen_at)
    VALUES (NEW.ip_address, 1, new_paths, NEW.occurred_at, NEW.occurred_at)
    ON CONFLICT (ip_address) DO UPDATE SET
        requests = a.requests + 1,
        distinct_paths = a.distinct_paths + EXCLUDED.distinct_paths,
        first_seen_at = LEAST(a.first_seen_at, EXCLUDED.first_seen_at),
        last_seen_at = GREATEST(a.last_seen_at, EXCLUDED.last_seen_at);
    RETURN NULL;
END
$$;

CREATE TRIGGER trg_telemetry_hits_count_ip
    AFTER INSERT ON telemetry_hits
    FOR EACH ROW WHEN (NEW.router_group = 'honeypot')
    EXECUTE FUNCTION count_ip_request();

CREATE FUNCTION count_ip_login_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO ip_activity AS a (ip_address, login_attempts)
    VALUES (NEW.ip_address, 1)
    ON CONFLICT (ip_address) DO UPDATE SET login_attempts = a.login_attempts + 1;
    RETURN NULL;
END
$$;

CREATE TRIGGER trg_credential_attempts_count_ip
    AFTER INSERT ON credential_stuffing_attempts
    FOR EACH ROW
    EXECUTE FUNCTION count_ip_login_attempt();

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

-- The migrations applied to this database, one row each, written by db/schema.py with the file's
-- SHA-256. A development reset records every migration, because it applies this file instead.
CREATE TABLE schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    sha256     TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
