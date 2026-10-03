-- name: CreateTelemetryHit :exec
INSERT INTO telemetry_hits (
    ip_address, method, path, query, router_group, user_agent, headers, body, body_size, status_code,
    banned, rule_id
)
VALUES (
    sqlc.arg(ip_address), sqlc.arg(method), sqlc.arg(path), sqlc.narg(query), sqlc.arg(router_group),
    sqlc.arg(user_agent), sqlc.arg(headers), sqlc.narg(body), sqlc.narg(body_size), sqlc.arg(status_code),
    sqlc.arg(banned), sqlc.narg(rule_id)
);

-- A login attempt, linked to the canary its password was, if it was one, and to the latest install
-- whose account it opened (by username or email, as WordPress's login takes either), if any. The
-- decoy pretends to accept (was_fake_success) a login into an installed account, or into an author's
-- with their weak password (`author_password`, ingest.py). Returns that, and whether the login
-- named an installed account at all, whatever the password.
-- name: CreateCredentialStuffingAttempt :one
WITH opened AS (
    SELECT id FROM install_attempts
    WHERE (username = sqlc.arg(username) OR email = sqlc.arg(username))
      AND password = sqlc.arg(password)
    ORDER BY attempted_at DESC, id DESC
    LIMIT 1
)
INSERT INTO credential_stuffing_attempts (
    ip_address, endpoint_path, username, password, was_fake_success, canary_id, install_id
)
VALUES (
    sqlc.arg(ip_address), sqlc.arg(endpoint_path), sqlc.arg(username), sqlc.arg(password),
    sqlc.arg(author_password)::BOOLEAN OR EXISTS (SELECT 1 FROM opened),
    (SELECT id FROM canary_tokens WHERE token = sqlc.arg(password)),
    (SELECT id FROM opened)
)
RETURNING
    was_fake_success,
    EXISTS (
        SELECT 1 FROM install_attempts
        WHERE username = sqlc.arg(username) OR email = sqlc.arg(username)
    ) AS known_account;

-- name: CreateInstallAttempt :one
INSERT INTO install_attempts (
    ip_address, path, site_title, username, email, password, password_generated
)
VALUES (
    sqlc.arg(ip_address), sqlc.arg(path), sqlc.arg(site_title), sqlc.arg(username),
    sqlc.arg(email), sqlc.arg(password), sqlc.arg(password_generated)
)
RETURNING id;

-- name: CreateCanaryToken :exec
INSERT INTO canary_tokens (token, path, ip_address)
VALUES (sqlc.arg(token), sqlc.arg(path), sqlc.arg(ip_address));

-- How many login attempts an address has made since a time (ingest.py, the tarpit), read from the
-- (ip_address, attempted_at) index.
-- name: CountLoginAttemptsSince :one
SELECT count(*) AS attempts
FROM credential_stuffing_attempts
WHERE ip_address = sqlc.arg(ip_address)::inet AND attempted_at >= sqlc.arg(since)::timestamptz;

-- The admin login (auth.py) ------------------------------------------------------------------

-- A Google login in progress: the state it was sent with and its PKCE verifier.
-- name: CreateOAuthState :exec
INSERT INTO oauth_states (state, code_verifier, expires)
VALUES (sqlc.arg(state), sqlc.arg(code_verifier), sqlc.arg(expires));

-- A login's state, used once: deleted as it is read, so a replayed callback finds nothing.
-- name: TakeOAuthState :one
DELETE FROM oauth_states
WHERE state = sqlc.arg(state) AND expires > NOW()
RETURNING code_verifier;

-- name: PruneOAuthStates :exec
DELETE FROM oauth_states WHERE expires <= NOW();

-- An admin is their email, the identity ADMIN_EMAILS authorises: the Google account behind it is
-- recorded, and replaced if the email moves to another.
-- name: UpsertUser :one
INSERT INTO users (google_sub, email, name)
VALUES (sqlc.arg(google_sub), sqlc.arg(email), sqlc.arg(name))
ON CONFLICT (email)
DO UPDATE SET
    google_sub = EXCLUDED.google_sub,
    name = EXCLUDED.name,
    last_login = CURRENT_TIMESTAMP
RETURNING id;

-- The session's token is stored only as its SHA-256.
-- name: CreateSession :exec
INSERT INTO sessions (user_id, token_hash, expires)
VALUES (sqlc.arg(user_id), sqlc.arg(token_hash), sqlc.arg(expires));

-- The user of an unexpired session, marking the session used.
-- name: UseSession :one
UPDATE sessions s SET last_used = NOW()
FROM users u
WHERE s.token_hash = sqlc.arg(token_hash) AND s.expires > NOW() AND u.id = s.user_id
RETURNING u.id, u.email, u.name;

-- name: DeleteSession :exec
DELETE FROM sessions WHERE token_hash = sqlc.arg(token_hash);

-- name: PruneSessions :exec
DELETE FROM sessions WHERE expires <= NOW();

-- name: CreateAuditLogEntry :exec
INSERT INTO admin_audit_log (user_id, action, target_ip, details)
VALUES (sqlc.arg(user_id), sqlc.arg(action), sqlc.narg(target_ip), sqlc.arg(details));

-- Response rules (rules.py; written in admin.py) ------------------------------------------------

-- The rules the decoy's requests are checked against, in order: neither removed nor expired.
-- name: ListActiveRules :many
SELECT id, method, path_pattern, condition, status_code, content_type, headers::TEXT AS headers, body,
    delay_ms
FROM response_rules
WHERE removed_at IS NULL AND (expires IS NULL OR expires > NOW())
ORDER BY position, id;

-- Every rule not removed, for the admin area, with how many hits each answered.
-- name: ListRules :many
SELECT
    r.id, r.position, r.method, r.path_pattern, r.condition, r.status_code, r.content_type,
    r.headers::TEXT AS headers, r.body, r.delay_ms, r.expires, r.note, r.updated,
    (SELECT count(*) FROM telemetry_hits h WHERE h.rule_id = r.id) AS hits
FROM response_rules r
WHERE r.removed_at IS NULL
ORDER BY r.position, r.id;

-- name: CreateRule :one
INSERT INTO response_rules (
    position, method, path_pattern, condition, status_code, content_type, headers, body, delay_ms,
    expires, note, created_by_user_id
)
VALUES (
    (SELECT COALESCE(max(position), 0) + 1 FROM response_rules),
    sqlc.narg(method), sqlc.narg(path_pattern), sqlc.arg(condition), sqlc.arg(status_code),
    sqlc.arg(content_type), sqlc.arg(headers), sqlc.arg(body), sqlc.arg(delay_ms),
    sqlc.narg(expires), sqlc.narg(note), sqlc.arg(created_by_user_id)
)
RETURNING id;

-- No row if there is no such rule, or it was removed.
-- name: UpdateRule :one
UPDATE response_rules
SET method = sqlc.narg(method), path_pattern = sqlc.narg(path_pattern),
    condition = sqlc.arg(condition), status_code = sqlc.arg(status_code),
    content_type = sqlc.arg(content_type), headers = sqlc.arg(headers), body = sqlc.arg(body),
    delay_ms = sqlc.arg(delay_ms), expires = sqlc.narg(expires), note = sqlc.narg(note),
    updated = NOW()
WHERE id = sqlc.arg(id) AND removed_at IS NULL
RETURNING id;

-- name: SetRulePosition :exec
UPDATE response_rules SET position = sqlc.arg(position) WHERE id = sqlc.arg(id);

-- No row if there is no such rule, or it was removed already.
-- name: RemoveRule :one
UPDATE response_rules SET removed_at = NOW()
WHERE id = sqlc.arg(id) AND removed_at IS NULL
RETURNING id;

-- What the response rules' markers say about a visitor (rules.py): its location and network, its
-- running totals, its logins since a time, and whether it was ever handed a canary or banned.
-- One row, whatever the address; NULLs where nothing is known.
-- name: GetVisitorFacts :one
SELECT
    l.country_code, l.city, l.asn, l.as_organisation, a.requests, a.first_seen_at,
    (SELECT count(*) FROM credential_stuffing_attempts c
     WHERE c.ip_address = v.ip AND c.attempted_at >= sqlc.arg(logins_since)::timestamptz) AS logins,
    EXISTS (SELECT 1 FROM canary_tokens t WHERE t.ip_address = v.ip) AS has_canary,
    EXISTS (SELECT 1 FROM ip_bans b WHERE b.ip_address = v.ip) AS banned_before
FROM (SELECT sqlc.arg(ip_address)::inet AS ip) v
LEFT JOIN ip_locations l ON l.ip_address = v.ip
LEFT JOIN ip_activity a ON a.ip_address = v.ip;

-- The latest admin actions, newest first.
-- name: ListAuditLog :many
SELECT l.id, l.logged_at, u.email, l.action, l.target_ip, l.details::TEXT AS details
FROM admin_audit_log l
JOIN users u ON u.id = l.user_id
ORDER BY l.logged_at DESC, l.id DESC
LIMIT sqlc.arg(limit_);

-- Bans (admin.py; the decoy asks through ingest.py) ---------------------------------------------
-- A ban is active until it expires or is revoked: the condition idx_ip_bans_active serves.

-- name: IsIpBanned :one
SELECT EXISTS (
    SELECT 1 FROM ip_bans
    WHERE ip_address = sqlc.arg(ip_address)::inet
      AND revoked_at IS NULL AND (expires IS NULL OR expires > NOW())
) AS banned;

-- A new ban, unless the address already has an active one (no row then).
-- name: CreateIpBan :one
INSERT INTO ip_bans (ip_address, expires, reason, added_by_user_id)
SELECT sqlc.arg(ip_address)::inet, sqlc.narg(expires), sqlc.narg(reason), sqlc.arg(added_by_user_id)
WHERE NOT EXISTS (
    SELECT 1 FROM ip_bans
    WHERE ip_address = sqlc.arg(ip_address)::inet
      AND revoked_at IS NULL AND (expires IS NULL OR expires > NOW())
)
RETURNING id;

-- Ends an active ban; no row if there is none with that id.
-- name: RevokeIpBan :one
UPDATE ip_bans
SET revoked_at = NOW(), revoked_by_user_id = sqlc.arg(revoked_by_user_id),
    revocation_reason = sqlc.narg(revocation_reason)
WHERE id = sqlc.arg(id)
  AND revoked_at IS NULL AND (expires IS NULL OR expires > NOW())
RETURNING ip_address;

-- An address's active ban, as the public exhibit shows it: when, never why or by whom.
-- name: GetActiveIpBan :one
SELECT added, expires
FROM ip_bans
WHERE ip_address = sqlc.arg(ip_address)::inet
  AND revoked_at IS NULL AND (expires IS NULL OR expires > NOW())
ORDER BY added
LIMIT 1;

-- Bans in full, for the admin area: one address's (every one, newest first), or with no address,
-- every active one.
-- name: ListIpBans :many
SELECT
    b.id, b.ip_address, b.added, b.expires, b.reason, a.email AS added_by, b.revoked_at,
    r.email AS revoked_by, b.revocation_reason,
    b.revoked_at IS NULL AND (b.expires IS NULL OR b.expires > NOW()) AS active
FROM ip_bans b
JOIN users a ON a.id = b.added_by_user_id
LEFT JOIN users r ON r.id = b.revoked_by_user_id
WHERE CASE
    WHEN sqlc.narg(ip_address)::inet IS NULL
        THEN b.revoked_at IS NULL AND (b.expires IS NULL OR b.expires > NOW())
    ELSE b.ip_address = sqlc.narg(ip_address)::inet
END
ORDER BY b.added DESC, b.id DESC;

-- Every event a visitor caused, newest first: requests to the honeypot, login attempts and
-- installs. Details are fetched separately, per kind (below). Bans are the
-- project's own actions, not a visitor's, so they are not listed.
--
-- Keyset paging: a page is the events after a cursor, the previous page's last event (events.py,
-- EventCursor), or a time after every event for the first page. (occurred_at, kind, id) is unique,
-- so rows never repeat or vanish between pages, however many events arrive meanwhile. Each kind is
-- its own sub-select with its own LIMIT, read newest first from its (time, id) index, and the
-- separate `<=` on the time lets that index scan start at the cursor: a page reads about one page
-- of rows from each table, however deep it is. (One UNION ALL view over the tables let the
-- planner read and sort a whole table instead.)
-- name: ListRecentEvents :many
SELECT * FROM (
    (SELECT 'hit'::event_kind AS kind, id, ip_address, occurred_at
     FROM telemetry_hits
     WHERE router_group = 'honeypot' AND is_public_address(ip_address) AND occurred_at <= sqlc.arg(before_at)::timestamptz
       AND (occurred_at, 'hit'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY occurred_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'login_attempt'::event_kind AS kind, id, ip_address, attempted_at AS occurred_at
     FROM credential_stuffing_attempts
     WHERE is_public_address(ip_address) AND attempted_at <= sqlc.arg(before_at)::timestamptz
       AND (attempted_at, 'login_attempt'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY attempted_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'install_attempt'::event_kind AS kind, id, ip_address, attempted_at AS occurred_at
     FROM install_attempts
     WHERE is_public_address(ip_address) AND attempted_at <= sqlc.arg(before_at)::timestamptz
       AND (attempted_at, 'install_attempt'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY attempted_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
) AS page
ORDER BY occurred_at DESC, kind DESC, id DESC
LIMIT sqlc.arg('limit')::int;

-- name: ListIpEvents :many
SELECT * FROM (
    (SELECT 'hit'::event_kind AS kind, id, ip_address, occurred_at
     FROM telemetry_hits
     WHERE router_group = 'honeypot' AND ip_address = sqlc.arg(ip_address)::inet AND is_public_address(ip_address) AND occurred_at <= sqlc.arg(before_at)::timestamptz
       AND (occurred_at, 'hit'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY occurred_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'login_attempt'::event_kind AS kind, id, ip_address, attempted_at AS occurred_at
     FROM credential_stuffing_attempts
     WHERE ip_address = sqlc.arg(ip_address)::inet AND is_public_address(ip_address) AND attempted_at <= sqlc.arg(before_at)::timestamptz
       AND (attempted_at, 'login_attempt'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
     ORDER BY attempted_at DESC, id DESC
     LIMIT sqlc.arg('limit')::int)
    UNION ALL
    (SELECT 'install_attempt'::event_kind AS kind, id, ip_address, attempted_at AS occurred_at
     FROM install_attempts
     WHERE ip_address = sqlc.arg(ip_address)::inet AND is_public_address(ip_address) AND attempted_at <= sqlc.arg(before_at)::timestamptz
       AND (attempted_at, 'install_attempt'::event_kind, id) < (sqlc.arg(before_at)::timestamptz, sqlc.arg(before_kind)::event_kind, sqlc.arg(before_id)::bigint)
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
    COALESCE(substring(body FROM 1 FOR 1024), ''::BYTEA)::BYTEA AS body_preview, body_size,
    path_category(path) AS category, banned,
    rule_id IS NOT NULL AS custom_response
FROM telemetry_hits
WHERE id = ANY(sqlc.arg(ids)::BIGINT[]);

-- With where its password was handed out, when it was a canary, and the install that created its
-- account, when it used one.
-- name: GetLoginAttemptsByIds :many
SELECT
    a.id, a.ip_address, a.attempted_at, a.endpoint_path, a.username, a.password,
    a.was_fake_success, c.path AS canary_path, c.ip_address AS canary_ip_address,
    c.issued_at AS canary_issued_at, i.id AS install_id, i.ip_address AS install_ip_address,
    i.attempted_at AS install_attempted_at
FROM credential_stuffing_attempts a
LEFT JOIN canary_tokens c ON c.id = a.canary_id AND is_public_address(c.ip_address)
LEFT JOIN install_attempts i ON i.id = a.install_id AND is_public_address(i.ip_address)
WHERE a.id = ANY(sqlc.arg(ids)::BIGINT[]);

-- name: GetInstallAttemptsByIds :many
SELECT
    id, ip_address, attempted_at, path, site_title, username, email, password, password_generated
FROM install_attempts
WHERE id = ANY(sqlc.arg(ids)::BIGINT[]) AND is_public_address(ip_address);

-- The logins into one install's account, from any address, oldest first: what came of a takeover.
-- name: ListInstallLoginIds :many
SELECT id
FROM credential_stuffing_attempts
WHERE install_id = sqlc.arg(install_id) AND is_public_address(ip_address)
ORDER BY attempted_at, id
LIMIT sqlc.arg(max_rows);

-- name: CountInstallLogins :one
SELECT count(*) FROM credential_stuffing_attempts
WHERE install_id = sqlc.arg(install_id) AND is_public_address(ip_address);



-- One request in full, only if it is in the given router group (the exhibit shows honeypot hits).
-- `headers` as TEXT: psycopg decodes JSONB to a dict, where the generated row expects a str.
-- name: GetHit :one
SELECT
    id, ip_address, occurred_at, method, path, query, status_code, user_agent,
    headers::TEXT AS headers, body, body_size, path_category(path) AS category, banned,
    rule_id IS NOT NULL AS custom_response
FROM telemetry_hits
WHERE id = sqlc.arg(id) AND router_group = sqlc.arg(router_group) AND is_public_address(ip_address);

-- The category path_category() gives a path (src/tests/test_path_categories.py).
-- name: CategorisePath :one
SELECT path_category(sqlc.arg(path)::TEXT) AS category;

-- What one IP address did, in numbers (running totals, see schema.sql); no row if it did nothing.
-- name: GetIpActivity :one
SELECT
    requests, distinct_paths, login_attempts, install_attempts, first_seen_at, last_seen_at,
    banned_requests
FROM ip_activity
WHERE ip_address = sqlc.arg(ip_address)::inet AND is_public_address(ip_address);

-- An address's location (schema.sql, ip_locations), kept from the first time it was located.
-- name: CreateIpLocation :exec
INSERT INTO ip_locations (
    ip_address, country_code, city, latitude, longitude, asn, as_organisation, source
)
VALUES (
    sqlc.arg(ip_address), sqlc.narg(country_code), sqlc.narg(city), sqlc.narg(latitude),
    sqlc.narg(longitude), sqlc.narg(asn), sqlc.narg(as_organisation), sqlc.arg(source)
)
ON CONFLICT (ip_address) DO NOTHING;

-- The locations of the given addresses that have one.
-- name: GetIpLocations :many
SELECT
    ip_address, country_code, city, latitude, longitude, asn, as_organisation, source, located_at
FROM ip_locations
WHERE ip_address = ANY(sqlc.arg(ip_addresses)::INET[]);

-- Addresses that visited the honeypot but were never located (scripts/locate_ips.py).
-- name: ListUnlocatedAddresses :many
SELECT a.ip_address
FROM ip_activity a
WHERE NOT EXISTS (SELECT FROM ip_locations l WHERE l.ip_address = a.ip_address)
ORDER BY a.ip_address;

-- The Patterns page (patterns.py). All-time figures come from the running totals (ip_activity,
-- ip_request_paths, ip_locations), whose size grows with the number of addresses, not requests.
-- Figures over requests and login attempts read only those `since` a time, through the time
-- indexes, so their cost is bounded by how busy that window was, however long the history.

-- name: GetPatternTotals :one
SELECT
    COALESCE(sum(a.requests), 0)::BIGINT AS requests,
    COALESCE(sum(a.login_attempts), 0)::BIGINT AS login_attempts,
    COALESCE(sum(a.install_attempts), 0)::BIGINT AS install_attempts,
    count(*) AS addresses,
    count(DISTINCT l.country_code) AS countries
FROM ip_activity a
LEFT JOIN ip_locations l USING (ip_address)
WHERE is_public_address(a.ip_address);

-- The first and last request to the honeypot; no row before the first.
-- name: GetObservationSpan :one
SELECT min(first_seen_at)::TIMESTAMPTZ AS first_seen_at, max(last_seen_at)::TIMESTAMPTZ AS last_seen_at
FROM ip_activity
WHERE is_public_address(ip_address)
HAVING count(first_seen_at) > 0;

-- name: CountRequestsSince :one
SELECT count(*) AS requests
FROM telemetry_hits
WHERE router_group = 'honeypot' AND is_public_address(ip_address)
      AND occurred_at >= sqlc.arg(since)::TIMESTAMPTZ;

-- Each distinct path is categorised once (MATERIALIZED): left to itself, the planner runs
-- path_category() on every joined row, which on a busy week took seconds.
-- name: CountCategoriesSince :many
WITH visits AS MATERIALIZED (
    SELECT path, ip_address, count(*) AS requests
    FROM telemetry_hits
    WHERE router_group = 'honeypot' AND is_public_address(ip_address)
      AND occurred_at >= sqlc.arg(since)::TIMESTAMPTZ
    GROUP BY path, ip_address
), categories AS MATERIALIZED (
    SELECT path, path_category(path) AS category FROM (SELECT DISTINCT path FROM visits) p
)
SELECT c.category, sum(v.requests)::BIGINT AS requests, count(DISTINCT v.ip_address) AS addresses
FROM visits v
JOIN categories c USING (path)
GROUP BY c.category
ORDER BY requests DESC, c.category;

-- name: TopPathsSince :many
SELECT path, path_category(path) AS category, requests, addresses FROM (
    SELECT path, count(*) AS requests, count(DISTINCT ip_address) AS addresses
    FROM telemetry_hits
    WHERE router_group = 'honeypot' AND is_public_address(ip_address)
      AND occurred_at >= sqlc.arg(since)::TIMESTAMPTZ
    GROUP BY path
    ORDER BY requests DESC, path
    LIMIT sqlc.arg('limit')::INT
) top;

-- name: TopUserAgentsSince :many
SELECT user_agent, count(*) AS requests, count(DISTINCT ip_address) AS addresses
FROM telemetry_hits
WHERE router_group = 'honeypot' AND is_public_address(ip_address)
      AND occurred_at >= sqlc.arg(since)::TIMESTAMPTZ
GROUP BY user_agent
ORDER BY requests DESC, user_agent
LIMIT sqlc.arg('limit')::INT;

-- Hours with no requests have no row.
-- name: CountRequestsPerHourSince :many
SELECT date_trunc('hour', occurred_at)::TIMESTAMPTZ AS hour, count(*) AS requests
FROM telemetry_hits
WHERE router_group = 'honeypot' AND is_public_address(ip_address)
      AND occurred_at >= sqlc.arg(since)::TIMESTAMPTZ
GROUP BY hour
ORDER BY hour;

-- name: TopUsernamesSince :many
SELECT username AS value, count(*) AS attempts, count(DISTINCT ip_address) AS addresses
FROM credential_stuffing_attempts
WHERE attempted_at >= sqlc.arg(since)::TIMESTAMPTZ AND is_public_address(ip_address)
GROUP BY username
ORDER BY attempts DESC, username
LIMIT sqlc.arg('limit')::INT;

-- name: TopPasswordsSince :many
SELECT password AS value, count(*) AS attempts, count(DISTINCT ip_address) AS addresses
FROM credential_stuffing_attempts
WHERE attempted_at >= sqlc.arg(since)::TIMESTAMPTZ AND is_public_address(ip_address)
GROUP BY password
ORDER BY attempts DESC, password
LIMIT sqlc.arg('limit')::INT;

-- Addresses never located, or whose country isn't known, count under a NULL country.
-- name: TopCountries :many
SELECT l.country_code, sum(a.requests)::BIGINT AS requests, count(*) AS addresses
FROM ip_activity a
LEFT JOIN ip_locations l USING (ip_address)
WHERE is_public_address(a.ip_address)
GROUP BY l.country_code
ORDER BY requests DESC, l.country_code
LIMIT sqlc.arg('limit')::INT;

-- name: TopNetworks :many
SELECT l.asn, l.as_organisation, sum(a.requests)::BIGINT AS requests, count(*) AS addresses
FROM ip_activity a
LEFT JOIN ip_locations l USING (ip_address)
WHERE is_public_address(a.ip_address)
GROUP BY l.asn, l.as_organisation
ORDER BY requests DESC, l.asn
LIMIT sqlc.arg('limit')::INT;

-- name: BusiestAddresses :many
SELECT
    a.ip_address, a.requests, a.distinct_paths, a.login_attempts, a.first_seen_at,
    a.last_seen_at, l.country_code
FROM ip_activity a
LEFT JOIN ip_locations l USING (ip_address)
WHERE is_public_address(a.ip_address)
ORDER BY a.requests DESC, a.ip_address
LIMIT sqlc.arg('limit')::INT;

-- The addresses seen over the longest time, first request to last.
-- name: LongestSeenAddresses :many
SELECT
    a.ip_address, a.requests, a.distinct_paths, a.login_attempts, a.first_seen_at,
    a.last_seen_at, l.country_code
FROM ip_activity a
LEFT JOIN ip_locations l USING (ip_address)
WHERE a.first_seen_at IS NOT NULL AND is_public_address(a.ip_address)
ORDER BY a.last_seen_at - a.first_seen_at DESC, a.ip_address
LIMIT sqlc.arg('limit')::INT;

-- Groups of addresses that each requested exactly the same set of paths, at least `min_paths` of
-- them: one tool, run from several machines. A path set is identified by the MD5s of its paths
-- (ip_request_paths), sorted. `example_address` is the group's quietest address, whose paths are
-- the cheapest to list (ListPathsOf).
-- name: ListToolkits :many
WITH path_sets AS (
    SELECT ip_address, md5(string_agg(path_md5::TEXT, ',' ORDER BY path_md5)) AS path_set,
           count(*) AS paths
    FROM ip_request_paths
    WHERE is_public_address(ip_address)
    GROUP BY ip_address
    HAVING count(*) >= sqlc.arg(min_paths)::INT
)
SELECT
    max(s.paths)::BIGINT AS paths,
    count(*) AS address_count,
    (array_agg(s.ip_address ORDER BY a.requests DESC, s.ip_address))[1:sqlc.arg(max_addresses)::INT]::INET[]
        AS addresses,
    (array_agg(s.ip_address ORDER BY a.requests, s.ip_address))[1]::INET AS example_address
FROM path_sets s
JOIN ip_activity a USING (ip_address)
GROUP BY s.path_set
HAVING count(*) >= 2
ORDER BY address_count DESC, paths DESC
LIMIT sqlc.arg('limit')::INT;

-- name: ListPathsOf :many
SELECT DISTINCT path
FROM telemetry_hits
WHERE ip_address = sqlc.arg(ip_address)::INET AND router_group = 'honeypot'
  AND is_public_address(ip_address)
ORDER BY path
LIMIT sqlc.arg('limit')::INT;

-- Where the located addresses are, one point per place (DB-IP gives a city's coordinates).
-- name: ListMapPlaces :many
SELECT
    l.latitude::FLOAT8 AS latitude, l.longitude::FLOAT8 AS longitude, l.city, l.country_code,
    sum(a.requests)::BIGINT AS requests, count(*) AS addresses
FROM ip_activity a
JOIN ip_locations l USING (ip_address)
WHERE l.latitude IS NOT NULL AND is_public_address(a.ip_address)
GROUP BY l.latitude, l.longitude, l.city, l.country_code
ORDER BY requests DESC
LIMIT sqlc.arg('limit')::INT;

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
