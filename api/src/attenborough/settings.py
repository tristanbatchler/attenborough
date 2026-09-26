from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Self, cast

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticUndefined
from pydantic_settings import BaseSettings, SettingsConfigDict

app_directory = Path(__file__).parent.parent.parent
settings_path = app_directory / ".env"
example_settings_path = app_directory / ".example.env"

_ADMIN_EMAILS_VALIDATION_ALIAS = "ADMIN_EMAILS"
# PostgreSQL `int` (int4): queries.sql casts LIMIT and OFFSET with `::int`.
_POSTGRES_INT_MAX = 2**31 - 1


class _Settings(BaseSettings):
    @field_validator(_ADMIN_EMAILS_VALIDATION_ALIAS, mode="before")
    @classmethod
    def normalize_admin_emails(cls, v: object) -> set[str]:
        emails: list[str] = []
        if isinstance(v, str):
            emails = v.split(",")
        elif isinstance(v, Sequence) and v and isinstance(v[0], str):
            v = cast(Sequence[str], v)
            emails = list(v)
        else:
            raise ValueError(
                f"{_ADMIN_EMAILS_VALIDATION_ALIAS} must be a string or comma-separated list of strings"
            )

        return {e.strip().lower() for e in emails}

    @model_validator(mode="after")
    def validate_page_takes(self) -> Self:
        if self.APP_DEFAULT_PAGE_TAKE > self.APP_MAX_PAGE_TAKE:
            raise ValueError("APP_DEFAULT_PAGE_TAKE cannot exceed APP_MAX_PAGE_TAKE")
        return self

    @property
    def APP_MAX_PAGE(self) -> int:
        """The last page whose OFFSET still fits a PostgreSQL int at the largest allowed take."""
        return _POSTGRES_INT_MAX // self.APP_MAX_PAGE_TAKE + 1

    # Development only: DEBUG-level logging (INFO otherwise) and every router's /test debug route.
    # Keep it off in production: /test reveals the server's view of the request.
    DEBUG: bool = Field(default=False)
    DB_DATABASE: str = Field(default=...)
    DB_USERNAME: str = Field(default=...)
    DB_PASSWORD: str = Field(default=...)
    DB_HOST: str = Field(default=...)
    DB_PORT: int = Field(default=5432, ge=0, le=0xFFFF)
    DB_MIN_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_POOL_SIZE: int = Field(default=20, ge=1)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, gt=0)
    WEB_BASE_URL: str = Field(default=...)
    API_BASE_URL: str = Field(default=...)
    APP_MAX_PAGE_TAKE: int = Field(default=200, ge=1)
    APP_DEFAULT_PAGE_TAKE: int = Field(default=20, ge=1)
    GOOGLE_CLIENT_ID: str = Field(default=...)
    GOOGLE_CLIENT_SECRET: str = Field(default=...)
    APP_SESSION_DURATION_DAYS: int = Field(default=30, gt=0)
    APP_SESSION_COOKIE_SECURE: bool = Field(default=True)
    ADMIN_EMAILS: set[str] = Field(
        default_factory=set, validation_alias=_ADMIN_EMAILS_VALIDATION_ALIAS
    )
    PASSWORD_LOCKOUT_EXPIRY_MINUTES: int = Field(default=15)
    PASSWORD_LOCKOUT_ATTEMPTS_THRESHOLD: int = Field(default=5)
    # Proxies allowed to report the client address via X-Forwarded-For: comma-separated IPs, CIDRs
    # or literals, as uvicorn's --forwarded-allow-ips (same name as its env var). Any other peer is
    # attributed to its own address. "*" trusts every peer, so it is only safe if the app can never
    # be reached except through the proxy. See api/README.md.
    FORWARDED_ALLOW_IPS: str = Field(default="127.0.0.1")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=settings_path,
        extra="ignore",
        env_ignore_empty=True,
    )


def _example_env() -> str:
    """The settings template: required fields blank, optional ones commented out with their default."""
    example_lines: list[str] = []
    for field_name, field_info in _Settings.model_fields.items():
        default = cast(object, field_info.default)
        if default is not PydanticUndefined:
            line = f"# {field_name} = {default} # Optional"
        else:
            line = f"{field_name} = "
        example_lines.append(line)
    return "\n".join(example_lines)


def write_example_env() -> None:
    """Rewrite the tracked .example.env from the fields above.

    Called once per server start, in main.py's lifespan (next to openapi.json), so a changed field
    shows up as a diff. Nothing else writes it: importing the app, tests and scripts don't.
    """
    _ = example_settings_path.write_text(_example_env())


@lru_cache
def get_settings() -> _Settings:
    """The settings, loaded and validated once.

    Without a .env, first creates one from the template and exits, so the user gets a file to fill
    in rather than a validation error for every required field.
    """
    if not settings_path.is_file():
        _ = settings_path.write_text(_example_env())
        logging.fatal(
            f"Settings file {settings_path} not present so I have created it for you - please fill out the required fields"
        )
        sys.exit(1)
    return _Settings()
