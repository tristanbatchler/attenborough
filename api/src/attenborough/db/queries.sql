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
    ip_address, method, path, query, router_group, user_agent, headers, body, body_size, status_code
)
VALUES (
    sqlc.arg(ip_address), sqlc.arg(method), sqlc.arg(path), sqlc.narg(query), sqlc.arg(router_group),
    sqlc.arg(user_agent), sqlc.arg(headers), sqlc.narg(body), sqlc.narg(body_size), sqlc.arg(status_code)
);

-- name: CreateCredentialStuffingAttempt :exec
INSERT INTO credential_stuffing_attempts (
    ip_address, endpoint_path, username, password, was_fake_success
)
VALUES (sqlc.arg(ip_address), sqlc.arg(endpoint_path), sqlc.arg(username), sqlc.arg(password), sqlc.arg(was_fake_success));

-- name: CreateActiveIpBan :one
INSERT INTO ip_bans (ip_address, expires, reason, added_by_user_id)
VALUES (sqlc.arg(ip_address), sqlc.arg(expires), sqlc.arg(reason), sqlc.arg(added_by_user_id))
RETURNING *;

-- Visitor events (the `visitor_events` view), newest first. The extra `kind, id` keeps the order
-- stable when events share a timestamp, so rows never repeat or vanish between pages.
-- name: ListRecentEvents :many
SELECT * FROM visitor_events
ORDER BY occurred_at DESC, kind, id DESC
LIMIT sqlc.arg('limit')::int
OFFSET sqlc.arg('offset')::int;

-- name: ListIpEvents :many
SELECT * FROM visitor_events
WHERE ip_address = sqlc.arg(ip_address)::inet
ORDER BY occurred_at DESC, kind, id DESC
LIMIT sqlc.arg('limit')::int
OFFSET sqlc.arg('offset')::int;

-- The details of one page's events, one query per kind. A hit's body is cut to its first KiB here,
-- and empty when none was captured (body_size is NULL then): sqlc can't type a nullable substring.
-- name: GetHitsByIds :many
SELECT
    id, ip_address, occurred_at, method, path, query, status_code, user_agent,
    COALESCE(substring(body FROM 1 FOR 1024), ''::BYTEA)::BYTEA AS body_preview, body_size
FROM telemetry_hits
WHERE id = ANY(sqlc.arg(ids)::BIGINT[]);

-- name: GetLoginAttemptsByIds :many
SELECT id, ip_address, attempted_at, endpoint_path, username, password, was_fake_success
FROM credential_stuffing_attempts
WHERE id = ANY(sqlc.arg(ids)::BIGINT[]);

-- name: GetDecoyViewsByIds :many
SELECT dv.id, dv.ip_address, dv.viewed_at, d.slug AS decoy_slug, d.type AS decoy_type
FROM decoy_views dv
INNER JOIN decoys d ON d.id = dv.decoy_id
WHERE dv.id = ANY(sqlc.arg(ids)::BIGINT[]);

-- name: GetDecoyPasswordAttemptsByIds :many
SELECT dpa.id, dpa.ip_address, dpa.attempted_at, d.slug AS decoy_slug, dpa.successful
FROM decoy_password_attempts dpa
INNER JOIN decoys d ON d.id = dpa.decoy_id
WHERE dpa.id = ANY(sqlc.arg(ids)::BIGINT[]);

-- One request in full, only if it is in the given router group (the exhibit shows honeypot hits).
-- `headers` as TEXT: psycopg decodes JSONB to a dict, where the generated row expects a str.
-- name: GetHit :one
SELECT
    id, ip_address, occurred_at, method, path, query, status_code, user_agent,
    headers::TEXT AS headers, body, body_size
FROM telemetry_hits
WHERE id = sqlc.arg(id) AND router_group = sqlc.arg(router_group);

-- What one IP address did, in numbers; no row if it sent no requests in the router group.
-- name: GetIpSummary :one
SELECT
    COUNT(*)::BIGINT AS requests,
    COUNT(DISTINCT path)::BIGINT AS distinct_paths,
    (SELECT COUNT(*) FROM credential_stuffing_attempts csa
     WHERE csa.ip_address = sqlc.arg(ip_address)::inet)::BIGINT AS login_attempts,
    MIN(occurred_at)::TIMESTAMPTZ AS first_seen_at,
    MAX(occurred_at)::TIMESTAMPTZ AS last_seen_at
FROM telemetry_hits
WHERE ip_address = sqlc.arg(ip_address)::inet AND router_group = sqlc.arg(router_group)
GROUP BY ip_address;

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
