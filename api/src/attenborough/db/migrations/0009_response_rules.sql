-- Response rules, written in the admin area (rules.py), and the end of stashit's unused decoy
-- tables: stage 2 of docs/plan-admin.md.

DROP TABLE decoy_views, decoy_password_attempts, decoy_lockouts, decoy_configs,
    decoy_text_contents, decoy_binary_paths, decoy_revocations, decoys;
DROP TYPE decoy_type;

-- No column has this type: the event listings only cast to it.
DROP TYPE event_kind;
CREATE TYPE event_kind AS ENUM ('hit', 'login_attempt', 'install_attempt');

ALTER TYPE audit_action RENAME TO audit_action_old;
CREATE TYPE audit_action AS ENUM (
    'login', 'ban_created', 'ban_revoked', 'rule_created', 'rule_changed', 'rule_removed'
);
ALTER TABLE admin_audit_log ALTER COLUMN action TYPE audit_action USING action::TEXT::audit_action;
DROP TYPE audit_action_old;

CREATE TABLE response_rules (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    position           INTEGER NOT NULL,
    method             TEXT,
    path_pattern       TEXT,
    condition          TEXT NOT NULL DEFAULT '',
    status_code        INTEGER NOT NULL,
    content_type       TEXT NOT NULL,
    headers            JSONB NOT NULL DEFAULT '{}'::jsonb,
    body               TEXT NOT NULL DEFAULT '',
    delay_ms           INTEGER NOT NULL DEFAULT 0,
    expires            TIMESTAMPTZ,
    note               TEXT,
    created_by_user_id BIGINT NOT NULL REFERENCES users (id),
    created            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    removed_at         TIMESTAMPTZ,

    CONSTRAINT chk_response_rules_status CHECK (status_code BETWEEN 200 AND 599),
    CONSTRAINT chk_response_rules_delay CHECK (delay_ms BETWEEN 0 AND 15000)
);

CREATE INDEX idx_response_rules_active ON response_rules (position) WHERE removed_at IS NULL;

ALTER TABLE telemetry_hits ADD COLUMN rule_id BIGINT REFERENCES response_rules (id);
CREATE INDEX idx_telemetry_hits_rule ON telemetry_hits (rule_id) WHERE rule_id IS NOT NULL;

-- has_canary, a rule marker.
CREATE INDEX idx_canary_tokens_ip ON canary_tokens (ip_address);
