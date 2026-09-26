from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import override

from fastapi import Request
from fastapi.routing import APIRouter
from starlette.responses import JSONResponse

from attenborough.dependencies import RequestOrigin
from attenborough.router.group import RouterGroup
from attenborough.util import ROOT_LOGGER_NAME, inherit_signature

logger = getLogger(name="attenborough.router.abstract")

_NAMESPACE_SEPARATOR = "."


def _dotted(*parts: str) -> str:
    """Join the non-empty parts into a dotted name: ("admin", "dashboard") -> "admin.dashboard"."""
    return _NAMESPACE_SEPARATOR.join(part for part in parts if part)


class Router(APIRouter, ABC):
    @inherit_signature(APIRouter.__init__)
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

        # This router's prefix as a dotted namespace, e.g. "/admin" -> "admin", "" -> "".
        self._namespace: str = (
            str(self.prefix).strip("/").replace("/", _NAMESPACE_SEPARATOR)
        )
        self.logger: Logger = getLogger(name=_dotted(ROOT_LOGGER_NAME, self._namespace))

        self._endpoint_registry: dict[Callable[..., object], str] = {}

        @self.get("/test")
        def test_route(request_origin: RequestOrigin):
            return JSONResponse(
                {
                    "prefix": self.prefix,
                    "logger_name": self.logger.name,
                    "server_time": datetime.now(tz=UTC).isoformat(),
                    "request_origin": str(request_origin),
                }
            )

    @property
    @abstractmethod
    def group(self) -> RouterGroup:
        pass

    @override
    @inherit_signature(APIRouter.add_api_route)
    def add_api_route(
        self,
        path: str,
        endpoint: Callable[..., object],
        *args: object,
        name: str | None = None,
        summary: str | None = None,
        openapi_extra: dict[str, object] | None = None,
        **kwargs: object,
    ):
        short_name = name or endpoint.__name__
        # Namespaced by this router ("admin.dashboard", "ip.get_ip_activity"): unique across
        # routers, which url_for relies on, and stable. main.py also uses it as the OpenAPI
        # operationId, so it names the generated frontend client's functions.
        route_name = _dotted(self._namespace, short_name)
        self._endpoint_registry[endpoint] = route_name

        # A new dict: never mutate the caller's. Read back by TelemetryMiddleware to classify each request.
        extra = {**(openapi_extra or {}), RouterGroup.header_key: self.group.value}

        return super().add_api_route(
            path,
            endpoint,
            *args,
            name=route_name,
            # FastAPI would title-case the qualified name; keep the readable short form.
            summary=summary or short_name.replace("_", " ").title(),
            **kwargs,
            openapi_extra=extra,
        )

    def url_for(
        self, request: Request, endpoint: Callable[..., object], **path_params: object
    ) -> str:
        if endpoint not in self._endpoint_registry:
            raise KeyError(
                f"Endpoint '{endpoint.__name__}' is not registered under this router."
            )

        unique_name = self._endpoint_registry[endpoint]
        return request.url_for(unique_name, **path_params).path
