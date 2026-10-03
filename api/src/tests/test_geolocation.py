from attenborough.geolocation import Databases, Geolocator, Location

IP = "178.128.226.173"
COUNTRY = "CA"
CITY = "Toronto"
ASN = 14061
NETWORK = "DigitalOcean, LLC"
OTHER_COUNTRY = "NL"
SOURCE = "DB-IP City Lite (2026-09-01) and ASN Lite (2026-09-01)"

# Records as DB-IP's Lite databases hold them (trimmed), for one of the honeypot's visitors.
CITY_RECORD = {
    "city": {"names": {"en": CITY}},
    "continent": {"code": "NA", "names": {"en": "North America"}},
    "country": {
        "iso_code": COUNTRY,
        "is_in_european_union": False,
        "names": {"en": "Canada"},
    },
    "location": {"latitude": 43.6548, "longitude": -79.3885},
    "subdivisions": [{"names": {"en": "Ontario"}}],
}
ASN_RECORD = {
    "autonomous_system_number": ASN,
    "autonomous_system_organization": NETWORK,
}


class FakeDatabase:
    """A maxminddb Reader holding the given records."""

    def __init__(self, records: dict[str, object]) -> None:
        self.records: dict[str, object] = records

    def get(self, ip_address: str, /) -> object:
        return self.records.get(ip_address)

    def close(self) -> None:
        pass


DATABASES = Databases(
    city=FakeDatabase({IP: CITY_RECORD}),
    asn=FakeDatabase({IP: ASN_RECORD}),
    source=SOURCE,
)


def test_an_address_gets_its_country_city_coordinates_and_network():
    assert DATABASES.locate(IP) == Location(
        country_code=COUNTRY,
        city=CITY,
        latitude=43.6548,
        longitude=-79.3885,
        asn=ASN,
        as_organisation=NETWORK,
        source=SOURCE,
    )


def test_an_address_the_databases_dont_know_is_located_as_unknown():
    # Private addresses (a visitor on the honeypot's own network) aren't in the databases.
    assert DATABASES.locate("192.168.20.1") == Location(
        country_code=None,
        city=None,
        latitude=None,
        longitude=None,
        asn=None,
        as_organisation=None,
        source=SOURCE,
    )


def test_a_country_without_a_city_or_coordinates_is_kept():
    databases = Databases(
        city=FakeDatabase({IP: {"country": {"iso_code": OTHER_COUNTRY}}}),
        asn=FakeDatabase({}),
        source=SOURCE,
    )
    location = databases.locate(IP)
    assert (location.country_code, location.city, location.latitude) == (
        OTHER_COUNTRY,
        None,
        None,
    )


def test_without_a_directory_nothing_is_located():
    with Geolocator(None) as geolocator:
        assert geolocator.locate(IP) is None
