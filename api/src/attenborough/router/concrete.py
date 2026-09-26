from typing import override

from attenborough.router.abstract import Router
from attenborough.router.group import RouterGroup
from attenborough.util import relative_url_path


class ExhibitRouter(Router):
    @property
    @override
    def group(self) -> RouterGroup:
        return RouterGroup.EXHIBIT


class SystemRouter(Router):
    @property
    @override
    def group(self) -> RouterGroup:
        return RouterGroup.SYSTEM


class HoneypotRouter(Router):
    @property
    @override
    def group(self) -> RouterGroup:
        return RouterGroup.HONEYPOT

    def decoy_slug(self, path: str) -> str:
        """A decoy's stable identity in the database: its full URL path without the leading slash."""
        return relative_url_path(f"{self.prefix}{path}")
