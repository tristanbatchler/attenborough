-- The complete, current schema: what applying every file in migrations/ in order builds. sqlc
-- generates the query code from this file, and a development reset (db/schema.py:reset_schema)
-- applies it directly. Change it together with a new migration that makes the same change;
-- src/tests/test_migrations.py fails if the two disagree (column order included, since generated
-- rows are positional). See api/README.md, "Database".
--
-- Keep it plain DDL. No DO $$ blocks: sqlc doesn't execute them, so types created inside are
-- invisible to it and generated enums become typing.Any. IF NOT EXISTS only where a brand-new
-- schema can already have the object (extensions).

-- Extensions (a new database may inherit these from its template)
CREATE EXTENSION IF NOT EXISTS "citext";

-- Enum types
CREATE TYPE decoy_type AS ENUM ('text', 'binary', 'trap');
CREATE TYPE audit_action AS ENUM ('login', 'ban_created', 'ban_revoked', 'decoy_revoked', 'settings_changed');
-- What a request was for, recorded with each hit; a router's tags carry its group (sqlc generates
-- the RouterGroup enum the API uses). 'ingest' is the decoy app reporting its visitors' requests:
-- records, not visits, so it is never stored. 'admin' is the admin area (auth.py, admin.py), never
-- stored either: its requests carry the session token.
CREATE TYPE router_group AS ENUM ('exhibit', 'system', 'honeypot', 'ingest', 'admin');
-- The kinds of event the exhibit lists (queries.sql, ListRecentEvents).
CREATE TYPE event_kind AS ENUM (
    'hit', 'login_attempt', 'decoy_view', 'decoy_password_attempt', 'install_attempt'
);
-- What a request's path was after, as path_category() (below) guesses it.
CREATE TYPE path_category AS ENUM (
    'homepage', 'crawlers', 'secrets', 'backups', 'debug', 'exploits', 'wordpress', 'webshells',
    'logins', 'apis', 'other'
);

------------------------------------------------------------------
-- 1. AUTHENTICATION & USERS
------------------------------------------------------------------

CREATE TABLE users (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    google_sub  TEXT NOT NULL UNIQUE,
    email       CITEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL, 
    created     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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

    CONSTRAINT chk_oauth_states_expiry CHECK (expires > created)
);

CREATE INDEX idx_oauth_states_expires ON oauth_states (expires);

-- The app role may delete these two, and only these: a login's state is used once, logging out
-- ends a session, and expired ones are pruned. PUBLIC rather than a role name (names are
-- deployment settings): only roles with USAGE on the schema can reach them, which
-- deploy/database.sql gives the app role alone.
GRANT DELETE ON sessions, oauth_states TO PUBLIC;

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
    -- Whether the decoy refused the request because its address was banned (ingest.py, judge_visit).
    banned       BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT chk_telemetry_hits_body CHECK (
        (body IS NULL) = (body_size IS NULL) AND body_size >= octet_length(body)
    )
);

-- BRIN index is optimal for high-volume, append-only time-series telemetry
CREATE INDEX idx_telemetry_hits_brin ON telemetry_hits USING brin (occurred_at);
-- The exhibit's listings page through events newest first, by (time, id): see ListRecentEvents.
CREATE INDEX idx_telemetry_hits_ip ON telemetry_hits (ip_address, occurred_at DESC, id DESC);
CREATE INDEX idx_telemetry_hits_router ON telemetry_hits (router_group, occurred_at DESC, id DESC);

-- What a request's path was after: an inference from the path alone, as sent (a percent-encoded
-- probe such as /%2eenv is 'other'). The first rule that matches wins. Never stored, so changing a
-- rule (CREATE OR REPLACE in a new migration) recategorises every past request too.
CREATE FUNCTION path_category(path TEXT) RETURNS path_category
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN (CASE
    WHEN path = '/' THEN 'homepage'
    WHEN path ~* '^/(\.well-known/)?(robots\.txt|sitemap[^/]*\.xml|favicon[^/]*|apple-touch-icon[^/]*|(app-)?ads\.txt|sellers\.json|llms\.txt|humans\.txt|security\.txt)$'
        THEN 'crawlers'
    -- Credentials and configuration: dotfiles, environment files, deployment and app config.
    WHEN path ~* '(^|/)\.(env|git|svn|hg|aws|ssh|docker|npmrc|bash_history|bashrc|ftpconfig|remote-sync\.json|vscode|idea|ds_store)|\.env$|^/env(\.|$)|/@vite/env|(^|/)(wp-config\.php|config\.(json|js|ini|xml|env|ya?ml|php|inc\.php)|appsettings[^/]*\.json|secrets?\.(json|ya?ml)|user_secrets\.yml|credentials|database\.php|app\.php|aws\.(json|ya?ml)|docker-compose[^/]*\.ya?ml|dockerfile|\.gitlab-ci\.yml|package\.json|deploy\.sh|web\.xml|server\.key|id_(rsa|ed25519)|sftp(-config)?\.json|ftp-sync\.json|service\.pwd|env\.js|deployment-config\.json)'
        THEN 'secrets'
    WHEN path ~* '\.(sql|zip|tar|gz|tgz|rar|7z|bak|old|backup|save|swp|log)$' THEN 'backups'
    -- Debugging and diagnostics pages that leak a server's internals.
    WHEN path ~* 'php[-_]?info|(^|/)(info|i|pi)\.php|actuator|_profiler|telescope|trace\.axd|server-status|_ignition|rails/info|debug|heapdump|configprops|/manage(ment)?/env|^/(health|status|version|metrics)$'
        THEN 'debug'
    -- Probes for specific, known vulnerabilities: a curated list, from what the honeypot has seen.
    WHEN path ~* 'eval-stdin\.php|gponform|boaform|cgi-bin/luci|sdk/weblanguage|metadatauploader|/ecp/|meta-inf/|containers/json|hnap1|onvif|^/wsman|hello\.world|test\.hello|gravitysmtp|ztp_gate|cmdb/system|fgt_lang|nc_gina_ver|rdx_en\.json|druid/|geoserver|^/hudson|autodiscover|_layouts/|owa/auth/x\.js'
        THEN 'exploits'
    WHEN path ~* '(^|/)(wp-[^/]*|xmlrpc\.php)' THEN 'wordpress'
    -- Any other PHP file: most are guesses at a web shell someone else left behind.
    WHEN path ~* '\.php[0-9]?$' THEN 'webshells'
    -- Sign-in pages of VPNs, appliances and admin consoles.
    WHEN path ~* 'log[io]n|sign[-_]?in|auth|admin|console|portal|vpn|\+csco[et]\+|global-protect|dana-na|^/remote|sonic|logonpoint|/owa/|rdweb|rashtml5|cpanel|whm|phpmyadmin|webui|webclient|dashboard\.jspa|^/iam/'
        THEN 'logins'
    WHEN path ~* '(^|/)(api|graphql|gql|v[0-9]+|mcp|sse|ws|rest)(/|$)|\.well-known/(mcp|agents?(-card)?\.json)|_catalog'
        THEN 'apis'
    ELSE 'other'
END)::path_category;

-- Secrets the decoy hands out in its "leaked" files (decoy/src/lib/server/leaks.ts): one fresh random
-- value per request, recorded against the address it was given to. They open nothing. If one is
-- ever submitted to a login form, the attempt is linked to it (credential_stuffing_attempts.
-- canary_id), so the exhibit can show where and when that password was picked up.
CREATE TABLE canary_tokens (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token      TEXT NOT NULL UNIQUE,
    -- The path it was served at, as requested.
    path       TEXT NOT NULL,
    ip_address INET NOT NULL,
    issued_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Someone finishing the decoy's "unfinished" WordPress install, to become the site's administrator:
-- the account they chose, as wp-admin/install.php took it. Nothing is installed. The submission
-- itself, as sent, is the body of its hit. If the account is later used to log in, the attempt is
-- linked to it (credential_stuffing_attempts.install_id).
CREATE TABLE install_attempts (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ip_address         INET NOT NULL,
    -- The installer's path, as requested.
    path               TEXT NOT NULL,
    site_title         TEXT NOT NULL,
    username           TEXT NOT NULL,
    email              TEXT NOT NULL,
    -- The account's password: the one chosen (trimmed, as WordPress stores it), or the one made up
    -- for it when none was, which the installer shows (password_generated).
    password           TEXT NOT NULL,
    password_generated BOOLEAN NOT NULL,
    attempted_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_install_attempts_ip ON install_attempts (ip_address, attempted_at DESC, id DESC);
CREATE INDEX idx_install_attempts_time ON install_attempts (attempted_at DESC, id DESC);
-- Every login is matched against the accounts installs created, by username or email
-- (CreateCredentialStuffingAttempt).
CREATE INDEX idx_install_attempts_username ON install_attempts (username);
CREATE INDEX idx_install_attempts_email ON install_attempts (email);

-- Specialized logging for credential stuffing & brute force attempts on /honeypot/admin/login or /auth
CREATE TABLE credential_stuffing_attempts (
    id BIGSERIAL PRIMARY KEY,
    ip_address INET NOT NULL,
    endpoint_path TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    was_fake_success BOOLEAN NOT NULL DEFAULT FALSE,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- The canary (canary_tokens) the password was, if any.
    canary_id BIGINT REFERENCES canary_tokens (id),
    -- The install (install_attempts) whose account it used, if any.
    install_id BIGINT REFERENCES install_attempts (id)
);

CREATE INDEX idx_credential_attempts_ip ON credential_stuffing_attempts (ip_address, attempted_at DESC, id DESC);
CREATE INDEX idx_credential_attempts_time ON credential_stuffing_attempts (attempted_at DESC, id DESC);
-- The logins into each install's account, in order (ListInstallLoginIds): a takeover's story.
CREATE INDEX idx_credential_attempts_install ON credential_stuffing_attempts (install_id, attempted_at, id)
    WHERE install_id IS NOT NULL;

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
    ip_address       INET PRIMARY KEY,
    -- Honeypot requests only, as the exhibit lists them.
    requests         BIGINT NOT NULL DEFAULT 0,
    distinct_paths   BIGINT NOT NULL DEFAULT 0,
    login_attempts   BIGINT NOT NULL DEFAULT 0,
    -- The first and last honeypot request; NULL while there are none.
    first_seen_at    TIMESTAMPTZ,
    last_seen_at     TIMESTAMPTZ,
    install_attempts BIGINT NOT NULL DEFAULT 0,
    -- Honeypot requests refused because the address was banned.
    banned_requests  BIGINT NOT NULL DEFAULT 0
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
    INSERT INTO ip_activity AS a (
        ip_address, requests, distinct_paths, first_seen_at, last_seen_at, banned_requests
    )
    VALUES (NEW.ip_address, 1, new_paths, NEW.occurred_at, NEW.occurred_at, NEW.banned::INTEGER)
    ON CONFLICT (ip_address) DO UPDATE SET
        requests = a.requests + 1,
        distinct_paths = a.distinct_paths + EXCLUDED.distinct_paths,
        first_seen_at = LEAST(a.first_seen_at, EXCLUDED.first_seen_at),
        last_seen_at = GREATEST(a.last_seen_at, EXCLUDED.last_seen_at),
        banned_requests = a.banned_requests + EXCLUDED.banned_requests;
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

CREATE FUNCTION count_ip_install_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO ip_activity AS a (ip_address, install_attempts)
    VALUES (NEW.ip_address, 1)
    ON CONFLICT (ip_address) DO UPDATE SET install_attempts = a.install_attempts + 1;
    RETURN NULL;
END
$$;

CREATE TRIGGER trg_install_attempts_count_ip
    AFTER INSERT ON install_attempts
    FOR EACH ROW
    EXECUTE FUNCTION count_ip_install_attempt();

-- Where each address that sent the honeypot a request is, and whose network it is in: derived from
-- a geolocation database (geolocation.py), never proof of where the sender is. Located once, when
-- its first request is recorded, and kept with the database it came from. No row: not located
-- (geolocation was off). A row of NULLs: the database had nothing for it.
CREATE TABLE ip_locations (
    ip_address      INET PRIMARY KEY,
    -- ISO 3166-1 alpha-2.
    country_code    TEXT,
    city            TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    -- The autonomous system (network) announcing the address, and who runs it.
    asn             BIGINT,
    as_organisation TEXT,
    -- Which databases said so, with the dates they were built.
    source          TEXT NOT NULL,
    located_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_ip_locations_coordinates CHECK ((latitude IS NULL) = (longitude IS NULL))
);

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
