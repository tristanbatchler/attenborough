from datetime import UTC, datetime
from logging import Logger, getLogger

from fastapi.routing import APIRouter
from starlette.responses import JSONResponse

from attenborough.dependencies import RequestOrigin
from attenborough.util import inherit_signature


class Router(APIRouter):
    @inherit_signature(APIRouter.__init__)
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        logger_name = "attenborough" + self.prefix.replace("/", ".")
        self.logger: Logger = getLogger(name=logger_name)

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
