from attenborough.exhibit.routers.feed import router as feed_router
from attenborough.exhibit.routers.ip import router as ip_router
from attenborough.exhibit.routers.meta import router as meta_router

exported_routers = [feed_router, ip_router, meta_router]
