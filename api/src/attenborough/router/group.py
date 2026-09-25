import enum


class RouterGroup(enum.StrEnum):
    header_key = enum.nonmember("header_group")

    EXHIBIT = "exhibit"
    SYSTEM = "system"
    HONEYPOT = "honeypot"
