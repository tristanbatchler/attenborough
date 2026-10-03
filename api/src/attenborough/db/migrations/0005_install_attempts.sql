-- Takeovers through the decoy's unfinished WordPress installer (decoy/src/lib/server/install.ts).

-- Last, so the listings' order of kinds (ListRecentEvents) stays as it was for the others. Nothing
-- here uses it: a value added in a transaction can't be used until it commits.
ALTER TYPE event_kind ADD VALUE 'install_attempt';

-- Someone finishing the decoy's "unfinished" WordPress install, to become the site's administrator:
-- the account they chose, as wp-admin/install.php took it. Nothing is installed. The submission
-- itself, as sent, is the body of its hit.
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

-- The install whose account a login attempt used, if any.
ALTER TABLE credential_stuffing_attempts
    ADD COLUMN install_id BIGINT REFERENCES install_attempts (id);
