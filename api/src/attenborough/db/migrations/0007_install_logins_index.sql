-- The logins into each install's account, in order (ListInstallLoginIds): a takeover's story.
CREATE INDEX idx_credential_attempts_install ON credential_stuffing_attempts (install_id, attempted_at, id)
    WHERE install_id IS NOT NULL;
