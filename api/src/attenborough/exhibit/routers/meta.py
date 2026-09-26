from attenborough import settings
from attenborough.response_models import ExhibitMeta
from attenborough.router import ExhibitRouter

router = ExhibitRouter(prefix="/meta")


@router.get("")
async def get_meta() -> ExhibitMeta:
    return ExhibitMeta(
        default_page_take=settings.APP_DEFAULT_PAGE_TAKE,
        max_page_take=settings.APP_MAX_PAGE_TAKE,
        max_page=settings.APP_MAX_PAGE,
    )
