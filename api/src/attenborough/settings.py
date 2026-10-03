from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, ClassVar, Self, cast

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticUndefined
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# api/ in a source checkout. Only a checkout has pyproject.toml beside the package: the container
# image installs the package into its virtual environment, where app_directory is somewhere else.
app_directory = Path(__file__).parent.parent.parent
settings_path = app_directory / ".env"
example_settings_path = app_directory / ".example.env"
# A source checkout reads api/.env (creating it from the template if missing) and, at server start,
# rewrites the tracked openapi.json and .example.env. An installed package (the container image)
# reads its settings from the environment only and writes nothing.
SOURCE_CHECKOUT = (app_directory / "pyproject.toml").is_file()

_HONEYPOT_ADDRESSES = "HONEYPOT_ADDRESSES"
_LIST_SEPARATOR = ","


class _Settings(BaseSettings):
    @field_validator(_HONEYPOT_ADDRESSES, mode="before")
    @classmethod
    def split_honeypot_addresses(cls, v: object) -> object:
        """A comma-separated string from the environment; the names are matched ignoring case."""
        if isinstance(v, str):
            return [name.strip() for name in v.split(_LIST_SEPARATOR) if name.strip()]
        return v

    @model_validator(mode="after")
    def validate_page_takes(self) -> Self:
        if self.APP_DEFAULT_PAGE_TAKE > self.APP_MAX_PAGE_TAKE:
            raise ValueError("APP_DEFAULT_PAGE_TAKE cannot exceed APP_MAX_PAGE_TAKE")
        return self

    # Development only: DEBUG-level logging (INFO otherwise) and every router's /test debug route.
    # Keep it off in production: /test reveals the server's view of the request.
    DEBUG: bool = Field(default=False)
    DB_DATABASE: str = Field(default=...)
    DB_USERNAME: str = Field(default=...)
    DB_PASSWORD: str = Field(default=...)
    # A host name or IP, or the directory holding PostgreSQL's unix socket (e.g. /var/run/postgresql,
    # as in the container deployment).
    DB_HOST: str = Field(default=...)
    DB_PORT: int = Field(default=5432, ge=0, le=0xFFFF)
    DB_MIN_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_POOL_SIZE: int = Field(default=20, ge=1)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30, gt=0)
    APP_MAX_PAGE_TAKE: int = Field(default=200, ge=1)
    APP_DEFAULT_PAGE_TAKE: int = Field(default=20, ge=1)
    # Every name and address the honeypot answers on (its domains and public IPs, past ones too),
    # comma-separated. The exhibit shows each as HONEYPOT_PLACEHOLDER wherever a visitor's request
    # contains it (events.py), so readers can't tell where the honeypot is. Required: forgetting it
    # would publish the honeypot's address. See api/README.md, "Hiding where the honeypot is".
    HONEYPOT_ADDRESSES: Annotated[list[str], NoDecode] = Field(
        default=..., min_length=1
    )
    # Proxies allowed to report the client address via X-Forwarded-For: comma-separated IPs, CIDRs
    # or literals, as uvicorn's --forwarded-allow-ips (same name as its env var). Any other peer is
    # attributed to its own address. "*" trusts every peer, so it is only safe if the app can never
    # be reached except through the proxy. See api/README.md.
    FORWARDED_ALLOW_IPS: str = Field(default="127.0.0.1")
    # The directory holding DB-IP's free Lite databases, dbip-city-lite.mmdb and dbip-asn-lite.mmdb
    # (geolocation.py; deploy/update-geoip.sh downloads them). Unset, no address is located.
    GEOIP_DIRECTORY: Path | None = Field(default=None)

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

    In a source checkout without a .env, first creates one from the template and exits, so the
    user gets a file to fill in rather than a validation error for every required field.
    """
    if SOURCE_CHECKOUT and not settings_path.is_file():
        _ = settings_path.write_text(_example_env())
        logging.fatal(
            f"Settings file {settings_path} not present so I have created it for you - please fill out the required fields"
        )
        sys.exit(1)
    return _Settings()
