-- name: UpsertUser :one
INSERT INTO users (google_sub, email, name, is_admin)
VALUES (sqlc.arg(google_sub), sqlc.arg(email), sqlc.arg(name), sqlc.arg(is_admin))
ON CONFLICT (google_sub)
DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name,
    last_login = CURRENT_TIMESTAMP,
    is_admin = EXCLUDED.is_admin
RETURNING *;

-- name: GetUserBySessionTokenHash :one
SELECT 
    u.id, u.google_sub, u.email, u.name, u.created, u.last_login, u.is_admin
FROM users u
INNER JOIN sessions s ON u.id = s.user_id
WHERE s.token_hash = sqlc.arg(token_hash)
  AND s.expires > NOW();

-- name: CreateTelemetryHit :exec
INSERT INTO telemetry_hits (
    ip_address, method, path, router_group, user_agent, headers, status_code
)
VALUES (sqlc.arg(ip_address), sqlc.arg(method), sqlc.arg(path), sqlc.arg(router_group), sqlc.arg(user_agent), sqlc.arg(headers), sqlc.arg(status_code));

-- name: CreateCredentialStuffingAttempt :exec
INSERT INTO credential_stuffing_attempts (
    ip_address, endpoint_path, username, password, was_fake_success
)
VALUES (sqlc.arg(ip_address), sqlc.arg(endpoint_path), sqlc.arg(username), sqlc.arg(password), sqlc.arg(was_fake_success));

-- name: GetIpThreatSummary :one
SELECT
    ip_address,
    COUNT(*)::BIGINT AS total_requests,
    COUNT(DISTINCT path)::BIGINT AS unique_endpoints_probed,
    MAX(occurred_at) AS last_seen_at
FROM telemetry_hits
WHERE ip_address = sqlc.arg(ip_address)::inet
GROUP BY ip_address;

-- name: CreateActiveIpBan :one
INSERT INTO ip_bans (ip_address, expires, reason, added_by_user_id)
VALUES (sqlc.arg(ip_address), sqlc.arg(expires), sqlc.arg(reason), sqlc.arg(added_by_user_id))
RETURNING *;

-- name: ListIpActivity :many
SELECT
    event_at,
    event_type,
    COALESCE(target_id, 0)::BIGINT AS target_id,
    COALESCE(target_slug, '')::TEXT AS target_slug,
    COALESCE(details, '')::TEXT AS details
FROM (
    -- 1. General Telemetry Hits (Path probes across routers)
    SELECT
        th.occurred_at AS event_at,
        ('hit_' || th.router_group)::TEXT AS event_type,
        NULL::BIGINT AS target_id,
        th.path::TEXT AS target_slug,
        ('status=' || th.status_code::text || ' | method=' || th.method)::TEXT AS details
    FROM telemetry_hits th
    WHERE th.ip_address = sqlc.arg(ip_address)::inet
      -- Only visitor traffic (the honeypot group), not the exhibit's or system's own requests.
      AND th.router_group = sqlc.arg(router_group)

    UNION ALL

    -- 2. Credential Stuffing / Login Probes
    SELECT
        csa.attempted_at AS event_at,
        CASE WHEN csa.was_fake_success THEN 'credential_stuffing_fake_success' ELSE 'credential_stuffing' END::TEXT AS event_type,
        NULL::BIGINT AS target_id,
        csa.endpoint_path::TEXT AS target_slug,
        ('username=' || csa.username || ' | password=' || csa.password)::TEXT AS details
    FROM credential_stuffing_attempts csa
    WHERE csa.ip_address = sqlc.arg(ip_address)::inet

    UNION ALL

    -- 3. Decoy Views / Downloads
    SELECT
        dv.viewed_at AS event_at,
        CASE WHEN d.type = 'binary' THEN 'decoy_downloaded' ELSE 'decoy_viewed' END::TEXT AS event_type,
        d.id::BIGINT AS target_id,
        d.slug::TEXT AS target_slug,
        NULL::TEXT AS details
    FROM decoy_views dv
    INNER JOIN decoys d ON d.id = dv.decoy_id
    WHERE dv.ip_address = sqlc.arg(ip_address)::inet

    UNION ALL

    -- 4. Decoy Password Attempts
    SELECT
        dpa.attempted_at AS event_at,
        CASE WHEN dpa.successful THEN 'decoy_password_success' ELSE 'decoy_password_failure' END::TEXT AS event_type,
        d.id::BIGINT AS target_id,
        d.slug::TEXT AS target_slug,
        NULL::TEXT AS details
    FROM decoy_password_attempts dpa
    INNER JOIN decoys d ON d.id = dpa.decoy_id
    WHERE dpa.ip_address = sqlc.arg(ip_address)::inet

    UNION ALL

    -- 5. IP Ban Actions
    SELECT
        b.added AS event_at,
        'ip_banned'::TEXT AS event_type,
        NULL::BIGINT AS target_id,
        NULL::TEXT AS target_slug,
        ('by_user_id=' || b.added_by_user_id::text || COALESCE(' | reason=' || NULLIF(b.reason, ''), ''))::TEXT AS details
    FROM ip_bans b
    WHERE b.ip_address = sqlc.arg(ip_address)::inet

    UNION ALL

    -- 6. IP Ban Revocations
    SELECT
        b.revoked_at AS event_at,
        'ip_ban_revoked'::TEXT AS event_type,
        NULL::BIGINT AS target_id,
        NULL::TEXT AS target_slug,
        ('by_user_id=' || b.revoked_by_user_id::text)::TEXT AS details
    FROM ip_bans b
    WHERE b.ip_address = sqlc.arg(ip_address)::inet
) events
WHERE event_at IS NOT NULL
ORDER BY event_at DESC
LIMIT sqlc.arg('limit')::int
OFFSET sqlc.arg('offset')::int;

-- name: ListRecentActivity :many
-- The latest visitor activity from every IP address, newest first: honeypot requests,
-- credential attempts, and decoy views and password attempts. Bans are the project's own
-- actions, not a visitor's, so they are not listed here.
SELECT
    event_at,
    event_type,
    host(ip_address)::TEXT AS ip_address,
    COALESCE(target_id, 0)::BIGINT AS target_id,
    COALESCE(target_slug, '')::TEXT AS target_slug,
    COALESCE(details, '')::TEXT AS details
FROM (
    SELECT
        th.occurred_at AS event_at,
        ('hit_' || th.router_group)::TEXT AS event_type,
        th.ip_address,
        NULL::BIGINT AS target_id,
        th.path::TEXT AS target_slug,
        ('status=' || th.status_code::text || ' | method=' || th.method)::TEXT AS details
    FROM telemetry_hits th
    WHERE th.router_group = sqlc.arg(router_group)

    UNION ALL

    SELECT
        csa.attempted_at AS event_at,
        CASE WHEN csa.was_fake_success THEN 'credential_stuffing_fake_success' ELSE 'credential_stuffing' END::TEXT AS event_type,
        csa.ip_address,
        NULL::BIGINT AS target_id,
        csa.endpoint_path::TEXT AS target_slug,
        ('username=' || csa.username || ' | password=' || csa.password)::TEXT AS details
    FROM credential_stuffing_attempts csa

    UNION ALL

    SELECT
        dv.viewed_at AS event_at,
        CASE WHEN d.type = 'binary' THEN 'decoy_downloaded' ELSE 'decoy_viewed' END::TEXT AS event_type,
        dv.ip_address,
        d.id::BIGINT AS target_id,
        d.slug::TEXT AS target_slug,
        NULL::TEXT AS details
    FROM decoy_views dv
    INNER JOIN decoys d ON d.id = dv.decoy_id

    UNION ALL

    SELECT
        dpa.attempted_at AS event_at,
        CASE WHEN dpa.successful THEN 'decoy_password_success' ELSE 'decoy_password_failure' END::TEXT AS event_type,
        dpa.ip_address,
        d.id::BIGINT AS target_id,
        d.slug::TEXT AS target_slug,
        NULL::TEXT AS details
    FROM decoy_password_attempts dpa
    INNER JOIN decoys d ON d.id = dpa.decoy_id
) events
ORDER BY event_at DESC
LIMIT sqlc.arg('limit')::int
OFFSET sqlc.arg('offset')::int;

-- name: UpsertDecoy :one
INSERT INTO decoys (type, slug, added_by_ip)
VALUES (sqlc.arg(type), sqlc.arg(slug), sqlc.arg(added_by_ip))
-- No-op update so RETURNING yields the existing id; added_by_ip stays the first visitor's.
ON CONFLICT (slug) DO UPDATE SET slug = decoys.slug
RETURNING id;

-- name: CreateDecoyView :exec
INSERT INTO decoy_views (decoy_id, ip_address)
VALUES (sqlc.arg(decoy_id), sqlc.arg(ip_address));

-- name: CreateDecoyPasswordAttempt :exec
INSERT INTO decoy_password_attempts (decoy_id, ip_address, successful)
VALUES (sqlc.arg(decoy_id), sqlc.arg(ip_address), sqlc.arg(successful));

-- Schema reset and fingerprint (used only by db/schema.py). DROP ... CASCADE also removes the
-- extensions installed in public; schema.sql recreates them.
-- name: DropPublicSchema :exec
DROP SCHEMA IF EXISTS public CASCADE;

-- name: CreatePublicSchema :exec
CREATE SCHEMA public;

-- name: GetSchemaFingerprint :one
SELECT sha256 FROM schema_fingerprint;

-- name: SetSchemaFingerprint :exec
INSERT INTO schema_fingerprint (sha256) VALUES (sqlc.arg(sha256));
