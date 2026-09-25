from typing import override

from attenborough.router.abstract import Router
from attenborough.router.group import RouterGroup


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
        return f"{self.prefix}{path}".removeprefix("/")
