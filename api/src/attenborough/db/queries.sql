-- name: UpsertUser :one
INSERT INTO users (google_sub, email, name, is_admin)
VALUES ($1, $2, $3, $4)
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
WHERE s.token_hash = $1 
  AND s.expires > NOW();

-- name: CreateTelemetryHit :exec
INSERT INTO telemetry_hits (
    ip_address, method, path, router_group, user_agent, headers, status_code
)
VALUES ($1, $2, $3, $4, $5, $6, $7);

-- name: CreateCredentialStuffingAttempt :exec
INSERT INTO credential_stuffing_attempts (
    ip_address, endpoint_path, username, password
)
VALUES ($1, $2, $3, $4);

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
VALUES ($1, $2, $3, $4)
RETURNING *;

-- name: ListIpActivity :many
SELECT
    event_at,
    event_type,
    COALESCE(target_id, 0)::BIGINT AS target_id,
    COALESCE(target_slug, '')::TEXT AS target_slug,
    details
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

    UNION ALL

    -- 2. Credential Stuffing / Login Probes
    SELECT
        csa.attempted_at AS event_at,
        'credential_stuffing'::TEXT AS event_type,
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