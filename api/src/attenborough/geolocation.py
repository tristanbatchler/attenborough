"""Where an address is, and whose network it is in, from DB-IP's free Lite databases: City Lite
(country, city, coordinates) and ASN Lite (the network's number and owner). They are MMDB files in
settings.GEOIP_DIRECTORY, licensed CC BY 4.0, so the exhibit credits DB-IP on every page.

A location is an estimate about an address, not a fact about who sent a request: most scanners run
in data centres, and the city is the data centre's. Each one is stored with the databases it came
from (schema.sql, ip_locations).

`geolocator` is opened for the server's lifetime (main.py's lifespan) and by scripts. Until then,
and without GEOIP_DIRECTORY, it locates nothing.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

from maxminddb.extension import Reader
from psycopg import AsyncConnection
from pydantic import BaseModel

from attenborough import settings
from attenborough.db import queries

logger = logging.getLogger(__name__)

# The files' names in GEOIP_DIRECTORY (deploy/update-geoip.sh downloads them under these names).
CITY_DATABASE = "dbip-city-lite.mmdb"
ASN_DATABASE = "dbip-asn-lite.mmdb"


# The parts of DB-IP's records used here. Any of them can be missing from a record.
class _Names(BaseModel):
    en: str | None = None


class _City(BaseModel):
    names: _Names = _Names()


class _Country(BaseModel):
    iso_code: str | None = None


class _Coordinates(BaseModel):
    latitude: float
    longitude: float


class _CityRecord(BaseModel):
    city: _City | None = None
    country: _Country | None = None
    location: _Coordinates | None = None


class _AsnRecord(BaseModel):
    autonomous_system_number: int | None = None
    autonomous_system_organization: str | None = None


class Database(Protocol):
    """What is used of a maxminddb Reader. Its own `get` returns a recursive type alias that type
    checkers can't resolve; records are validated by the models above instead."""

    def get(self, ip_address: str, /) -> object: ...
    def close(self) -> None: ...


def _record[M: BaseModel](database: Database, ip_address: str, model: type[M]) -> M:
    """The record for `ip_address`, empty if the database has none."""
    record = database.get(ip_address)
    return model() if record is None else model.model_validate(record)


@dataclass(frozen=True)
class Location:
    country_code: str | None
    city: str | None
    latitude: float | None
    longitude: float | None
    asn: int | None
    as_organisation: str | None
    # The databases it came from, with the dates they were built.
    source: str


@dataclass(frozen=True)
class Databases:
    """An open pair of databases: City Lite and ASN Lite."""

    city: Database
    asn: Database
    # Which they are, with the dates they were built.
    source: str

    def locate(self, ip_address: str) -> Location:
        """Where `ip_address` is, as far as the databases know: every field None if not at all."""
        city = _record(self.city, ip_address, _CityRecord)
        asn = _record(self.asn, ip_address, _AsnRecord)
        return Location(
            country_code=None if city.country is None else city.country.iso_code,
            city=None if city.city is None else city.city.names.en,
            latitude=None if city.location is None else city.location.latitude,
            longitude=None if city.location is None else city.location.longitude,
            asn=asn.autonomous_system_number,
            as_organisation=asn.autonomous_system_organization,
            source=self.source,
        )


def _built_on(reader: Reader) -> str:
    return datetime.fromtimestamp(reader.metadata().build_epoch, UTC).date().isoformat()


class Geolocator:
    """Looks addresses up in the databases in `directory`, while open. Use it as a context manager;
    it reads nothing until opened."""

    def __init__(self, directory: Path | None) -> None:
        self.directory: Path | None = directory
        self._open: Databases | None = None

    def open(self) -> None:
        """Raises FileNotFoundError if `directory` is set but lacks either database."""
        if self.directory is None:
            logger.info("GEOIP_DIRECTORY is not set: addresses won't be located")
            return
        city = Reader(self.directory / CITY_DATABASE)
        asn = Reader(self.directory / ASN_DATABASE)
        source = f"DB-IP City Lite ({_built_on(city)}) and ASN Lite ({_built_on(asn)})"
        self._open = Databases(city, asn, source)
        logger.info("Locating addresses with %s", source)

    def close(self) -> None:
        if self._open is not None:
            self._open.city.close()
            self._open.asn.close()
            self._open = None

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def locate(self, ip_address: str) -> Location | None:
        """Where `ip_address` is (Databases.locate); None while closed."""
        return None if self._open is None else self._open.locate(ip_address)


geolocator = Geolocator(settings.GEOIP_DIRECTORY)


async def record_location(conn: AsyncConnection, ip_address: str) -> None:
    """Locate `ip_address` and keep the result, unless it was located before. Does nothing while
    `geolocator` is closed."""
    location = geolocator.locate(ip_address)
    if location is None:
        return
    await queries.create_ip_location(
        conn,
        ip_address=ip_address,
        country_code=location.country_code,
        city=location.city,
        latitude=location.latitude,
        longitude=location.longitude,
        asn=location.asn,
        as_organisation=location.as_organisation,
        source=location.source,
    )
