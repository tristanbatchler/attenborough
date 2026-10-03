-- Geolocation: country, city and network per address (docs/plan-patterns.md).

-- Where each address that sent the honeypot a request is, and whose network it is in: derived from
-- a geolocation database (geolocation.py), never proof of where the sender is. Located once, when
-- its first request is recorded, and kept with the database it came from. No row: not located
-- (geolocation was off). A row of NULLs: the database had nothing for it.
CREATE TABLE ip_locations (
    ip_address      INET PRIMARY KEY,
    -- ISO 3166-1 alpha-2.
    country_code    TEXT,
    city            TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    -- The autonomous system (network) announcing the address, and who runs it.
    asn             BIGINT,
    as_organisation TEXT,
    -- Which databases said so, with the dates they were built.
    source          TEXT NOT NULL,
    located_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_ip_locations_coordinates CHECK ((latitude IS NULL) = (longitude IS NULL))
);
