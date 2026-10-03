-- The admin login (Google) and app-level bans: stage 1 of docs/plan-admin.md.

-- Only ADMIN_EMAILS may log in, checked against the setting on every request (auth.py): a flag
-- stored at login would outlive a change to the setting.
ALTER TABLE users DROP COLUMN is_admin;

-- Every login is started by the exhibit's web server, so this was always its address.
ALTER TABLE oauth_states DROP COLUMN ip_address;

-- The app role may delete these two, and only these: a login's state is used once, logging out
-- ends a session, and expired ones are pruned. PUBLIC rather than a role name (names are
-- deployment settings): only roles with USAGE on the schema can reach them, which
-- deploy/database.sql gives the app role alone.
GRANT DELETE ON sessions, oauth_states TO PUBLIC;

-- The admin area's requests (auth.py, admin.py).
ALTER TYPE router_group ADD VALUE 'admin';

-- Whether the decoy refused the request because its address was banned (ingest.py, judge_visit).
ALTER TABLE telemetry_hits ADD COLUMN banned BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE ip_activity ADD COLUMN banned_requests BIGINT NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION count_ip_request() RETURNS trigger LANGUAGE plpgsql AS $$
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
