from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from logging import Logger, getLogger
from typing import override
from uuid import uuid4

from fastapi import Request
from fastapi.routing import APIRouter
from starlette.responses import JSONResponse

from attenborough.dependencies import RequestOrigin
from attenborough.router.group import RouterGroup
from attenborough.util import inherit_signature

logger = getLogger(name="attenborough.router.abstract")


class Router(APIRouter, ABC):
    @inherit_signature(APIRouter.__init__)
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)

        prefix_str = str(self.prefix).replace("/", ".") if self.prefix else ""
        logger_name = f"attenborough{prefix_str}"
        self.logger: Logger = getLogger(name=logger_name)

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
        openapi_extra: dict[str, object] | None = None,
        **kwargs: object,
    ):
        uuid_str = uuid4().hex
        self._endpoint_registry[endpoint] = uuid_str

        # A new dict: never mutate the caller's. Read back by TelemetryMiddleware to classify each request.
        extra = {**(openapi_extra or {}), RouterGroup.header_key: self.group.value}

        return super().add_api_route(
            path, endpoint, *args, name=uuid_str, **kwargs, openapi_extra=extra
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
