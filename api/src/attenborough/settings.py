from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, cast

from pydantic import Field, field_validator
from pydantic_core import PydanticUndefined
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


app_directory = Path(__file__).parent.parent.parent
settings_path = app_directory / ".env"

_ADMIN_EMAILS_VALIDATION_ALIAS: str = "ADMIN_EMAILS"


class _Settings(BaseSettings):
    @field_validator(_ADMIN_EMAILS_VALIDATION_ALIAS, mode="before")
    @classmethod
    def normalize_admin_emails(cls, v: object) -> set[str]:
        emails: list[str] = []
        if isinstance(v, str):
            emails = v.split(",")
        elif isinstance(v, Sequence) and len(v) > 0 and isinstance(v[0], str):
            v = cast(Sequence[str], v)
            emails = list(v)
        else:
            raise ValueError(
                f"{_ADMIN_EMAILS_VALIDATION_ALIAS} must be a string or comma-separated list of strings"
            )

        return {e.strip().lower() for e in emails}

    DB_DATABASE: str = Field(default=...)
    DB_USERNAME: str = Field(default=...)
    DB_PASSWORD: str = Field(default=...)
    DB_HOST: str = Field(default=...)
    DB_PORT: int = Field(default=5432, ge=0, le=0xFFFF)
    WEB_BASE_URL: str = Field(default=...)
    API_BASE_URL: str = Field(default=...)
    APP_MAX_PAGE_TAKE: int = Field(default=200, ge=1)
    GOOGLE_CLIENT_ID: str = Field(default=...)
    GOOGLE_CLIENT_SECRET: str = Field(default=...)
    APP_SESSION_DURATION_DAYS: int = Field(default=30, gt=0)
    APP_SESSION_COOKIE_SECURE: bool = Field(default=True)
    ADMIN_EMAILS: set[str] = Field(
        default_factory=set, validation_alias=_ADMIN_EMAILS_VALIDATION_ALIAS
    )
    PASSWORD_LOCKOUT_EXPIRY_MINUTES: int = Field(default=15)
    PASSWORD_LOCKOUT_ATTEMPTS_THRESHOLD: int = Field(default=5)
    REAL_IP_HEADER: str = Field(default="X-Real-IP")

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=settings_path,
        extra="ignore",
        env_ignore_empty=True,
    )


def write_example(maybe_fail_and_copy: bool = False) -> None:
    # Write the settings example file based on Settings defaults
    example_lines: list[str] = []
    for field_name, field_info in _Settings.model_fields.items():
        default = cast(object, field_info.default)
        if default is not PydanticUndefined:
            line = f"# {field_name} = {default} # Optional"
        else:
            line = f"{field_name} = "
        example_lines.append(line)

    example_text = "\n".join(example_lines)
    example_settings_path = app_directory / ".example.env"
    _ = example_settings_path.write_text(example_text)

    # If the settings file doesn't exist, copy the example on there too
    if maybe_fail_and_copy and not settings_path.is_file():
        _ = settings_path.write_text(example_text)
        logging.fatal(
            f"Settings file {settings_path} not present so I have created it for you - please fill out the required fields"
        )
        sys.exit(1)

@lru_cache
def get_settings() -> _Settings:
    return _Settings()