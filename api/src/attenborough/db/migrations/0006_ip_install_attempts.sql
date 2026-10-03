-- Installs in the per-address running totals (ip_activity), kept like login_attempts.

ALTER TABLE ip_activity ADD COLUMN install_attempts BIGINT NOT NULL DEFAULT 0;

-- The installs recorded before the trigger existed.
INSERT INTO ip_activity AS a (ip_address, install_attempts)
SELECT ip_address, count(*) FROM install_attempts GROUP BY ip_address
ON CONFLICT (ip_address) DO UPDATE SET install_attempts = EXCLUDED.install_attempts;

CREATE FUNCTION count_ip_install_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO ip_activity AS a (ip_address, install_attempts)
    VALUES (NEW.ip_address, 1)
    ON CONFLICT (ip_address) DO UPDATE SET install_attempts = a.install_attempts + 1;
    RETURN NULL;
END
$$;

CREATE TRIGGER trg_install_attempts_count_ip
    AFTER INSERT ON install_attempts
    FOR EACH ROW
    EXECUTE FUNCTION count_ip_install_attempt();
