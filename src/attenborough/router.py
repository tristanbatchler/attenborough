from logging import Logger, getLogger

from fastapi.routing import APIRouter

from attenborough.util import inherit_signature


class Router(APIRouter):
    @inherit_signature(APIRouter.__init__)
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.logger: Logger = getLogger(name=__name__)
