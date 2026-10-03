-- Canary secrets in the decoy's leaked files (docs/plan-decoys.md).

-- Secrets the decoy hands out in its "leaked" files (/.env, /wp-config.php.bak): one fresh random
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

-- The canary a login attempt's password was, if any.
ALTER TABLE credential_stuffing_attempts
    ADD COLUMN canary_id BIGINT REFERENCES canary_tokens (id);
