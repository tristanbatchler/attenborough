-- Hide the project's own addresses from the exhibit (exhibit queries, queries.sql).

-- Whether the exhibit shows an address's activity: not a private, loopback or link-local one. Those
-- are the project's own, such as the admin testing the decoy from the LAN, reaching it through the
-- router's loopback (NAT hairpinning) as the router's address. Kept as recorded, never shown.
CREATE FUNCTION is_public_address(address INET) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN NOT address <<= ANY ('{10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16, ::1/128, fc00::/7, fe80::/10}'::INET[]);
