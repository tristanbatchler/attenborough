import enum


class RouterGroup(enum.StrEnum):
    header_key = enum.nonmember("header_group")

    EXHIBIT = "exhibit"
    SYSTEM = "system"
    HONEYPOT = "honeypot"
    # The decoy app (decoy/) reporting its visitors' requests: records, not visits.
    INGEST = "ingest"
