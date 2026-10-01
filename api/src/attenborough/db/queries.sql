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

-- Every event a visitor caused, newest first: requests to the honeypot, login attempts, decoy views
-- and decoy password attempts. Details are fetched separately, per kind (below). Bans are the
-- project's own actions, not a visitor's, so they are not listed.
--
-- Keyset paging: a page is the events after a cursor, the previous page's last event (events.py,
-- EventCursor), or a time after every event for the first page. (occurred_at, kind, id) is unique,
-- so rows never repeat or vanish between pages, however many events arrive meanwhile. Each kind is
-- its own sub-select with its own LIMIT, read newest first from its (time, id) index, and the
-- separate `<=` on the time lets that index scan start at the cursor: a page reads about one page
-- of rows from each table, however deep it is. (One UNION ALL view over the four tables let the
-- planner read and sort a whole table instead.)
-- name: ListRecentEvents :many
SELECT * FROM (
    (SELECT 'hit'::event_kind AS kind, id, ip_address, occurred_at
     FROM telemetry_hits
     WHERE router_group = 'honeypot' AND occurred_at <= sqlc.arg(before_at)::timestamptz
       AND (occurred_at, 'hit'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY occurred_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'login_attempt'::event_kind AS kind, id, ip_address, attempted_at AS occurred_at
     FROM credential_stuffing_attempts
     WHERE attempted_at <= sqlc.arg(before_at)::timestamptz
       AND (attempted_at, 'login_attempt'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY attempted_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'decoy_view'::event_kind AS kind, id, ip_address, viewed_at AS occurred_at
     FROM decoy_views
     WHERE viewed_at <= sqlc.arg(before_at)::timestamptz
       AND (viewed_at, 'decoy_view'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY viewed_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'decoy_password_attempt'::event_kind AS kind, id, ip_address, attempted_at AS occurred_at
     FROM decoy_password_attempts
     WHERE attempted_at <= sqlc.arg(before_at)::timestamptz
       AND (attempted_at, 'decoy_password_attempt'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY attempted_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
) AS page
ORDER BY occurred_at DESC, kind DESC, id DESC
LIMIT sqlc.arg('limit')::int;

-- name: ListIpEvents :many
SELECT * FROM (
    (SELECT 'hit'::event_kind AS kind, id, ip_address, occurred_at
     FROM telemetry_hits
     WHERE router_group = 'honeypot' AND ip_address = sqlc.arg(ip_address)::inet AND occurred_at <= sqlc.arg(before_at)::timestamptz
       AND (occurred_at, 'hit'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY occurred_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'login_attempt'::event_kind AS kind, id, ip_address, attempted_at AS occurred_at
     FROM credential_stuffing_attempts
     WHERE ip_address = sqlc.arg(ip_address)::inet AND attempted_at <= sqlc.arg(before_at)::timestamptz
       AND (attempted_at, 'login_attempt'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY attempted_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'decoy_view'::event_kind AS kind, id, ip_address, viewed_at AS occurred_at
     FROM decoy_views
     WHERE ip_address = sqlc.arg(ip_address)::inet AND viewed_at <= sqlc.arg(before_at)::timestamptz
       AND (viewed_at, 'decoy_view'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY viewed_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'decoy_password_attempt'::event_kind AS kind, id, ip_address, attempted_at AS occurred_at
     FROM decoy_password_attempts
     WHERE ip_address = sqlc.arg(ip_address)::inet AND attempted_at <= sqlc.arg(before_at)::timestamptz
       AND (attempted_at, 'decoy_password_attempt'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY attempted_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
) AS page
ORDER BY occurred_at DESC, kind DESC, id DESC
LIMIT sqlc.arg('limit')::int;

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

-- What one IP address did, in numbers (running totals, see schema.sql); no row if it did nothing.
-- name: GetIpActivity :one
SELECT requests, distinct_paths, login_attempts, first_seen_at, last_seen_at
FROM ip_activity
WHERE ip_address = sqlc.arg(ip_address)::inet;

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

-- Schema reset and migrations (used only by db/schema.py). DROP ... CASCADE also removes the
-- extensions installed in public; schema.sql recreates them.
-- name: DropPublicSchema :exec
DROP SCHEMA IF EXISTS public CASCADE;

-- name: CreatePublicSchema :exec
CREATE SCHEMA public;

-- name: ListAppliedMigrations :many
SELECT version, sha256 FROM schema_migrations ORDER BY version;

-- name: RecordMigration :exec
INSERT INTO schema_migrations (version, name, sha256)
VALUES (sqlc.arg(version), sqlc.arg(name), sqlc.arg(sha256));

-- Development only (scripts/seed_db.py): synthetic honeypot traffic, to measure the exhibit at
-- volume. Rows `start` + 1 to `start` + `count` of `total`, evenly spread in time over the `days`
-- before now and inserted in time order, as real traffic is. Each comes from the first address
-- with probability `busy_share`, else from one of `addresses` addresses counted up from it, the
-- lowest sending most (a cubed random draw: a few addresses send most requests). Mostly bodiless
-- GETs, and POSTs with bodies of mixed sizes, a few large.
-- name: SeedHits :exec
INSERT INTO telemetry_hits (
    ip_address, method, path, query, router_group, user_agent, headers, body, body_size,
    status_code, occurred_at
)
SELECT
    sqlc.arg(first_address)::inet + CASE
        WHEN random() < sqlc.arg(busy_share)::float8 THEN 0
        ELSE floor(sqlc.arg(addresses)::int * power(random(), 3))::int
    END,
    hit.method, hit.path, NULLIF(hit.query, ''), 'honeypot', hit.user_agent,
    jsonb_build_object('host', 'seed.invalid', 'user-agent', hit.user_agent),
    hit.body, octet_length(hit.body), hit.status_code,
    now() - make_interval(days => sqlc.arg(days)::int)
        + (n::float8 / sqlc.arg(total)::int) * make_interval(days => sqlc.arg(days)::int)
FROM generate_series(sqlc.arg(start)::int + 1, sqlc.arg(start)::int + sqlc.arg(count)::int) n
CROSS JOIN LATERAL (
    SELECT
        CASE WHEN r < 0.2 THEN 'POST' ELSE 'GET' END AS method,
        (ARRAY['/wp-login.php', '/.env', '/xmlrpc.php', '/phpmyadmin/', '/', '/admin',
               '/.git/config', '/cgi-bin/luci', '/boaform/admin/formLogin',
               '/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php'])[1 + floor(random() * 10)::int]
            AS path,
        CASE WHEN random() < 0.1 THEN 'id=' || n ELSE '' END AS query,
        (ARRAY['Mozilla/5.0 zgrab/0.x', 'curl/8.5.0', 'python-requests/2.32',
               'Go-http-client/1.1'])[1 + floor(random() * 4)::int] AS user_agent,
        CASE
            WHEN r >= 0.2 THEN ''::BYTEA
            WHEN random() < 0.01 THEN convert_to(repeat(md5(random()::text), 2048), 'UTF8')
            ELSE convert_to(repeat(md5(random()::text), 1 + floor(random() * 16)::int), 'UTF8')
        END AS body,
        CASE WHEN random() < 0.05 THEN 200 ELSE 404 END AS status_code
    FROM (SELECT random() AS r, n) draw
) hit
ORDER BY n;

-- Development only (scripts/seed_db.py): login attempts, spread like SeedHits.
-- name: SeedLoginAttempts :exec
INSERT INTO credential_stuffing_attempts (ip_address, endpoint_path, username, password, attempted_at)
SELECT
    sqlc.arg(first_address)::inet + CASE
        WHEN random() < sqlc.arg(busy_share)::float8 THEN 0
        ELSE floor(sqlc.arg(addresses)::int * power(random(), 3))::int
    END,
    '/wp-login.php',
    (ARRAY['admin', 'root', 'administrator', 'test', 'user'])[1 + floor(random() * 5)::int],
    (ARRAY['admin', '123456', 'password', 'admin123', 'qwerty'])[1 + floor(random() * 5)::int],
    now() - make_interval(days => sqlc.arg(days)::int)
        + (n::float8 / sqlc.arg(total)::int) * make_interval(days => sqlc.arg(days)::int)
FROM generate_series(sqlc.arg(start)::int + 1, sqlc.arg(start)::int + sqlc.arg(count)::int) n
ORDER BY n;
