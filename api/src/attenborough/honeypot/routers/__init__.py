from attenborough.honeypot.routers.admin import router as admin_router
from attenborough.honeypot.routers.auth import router as auth_router
from attenborough.honeypot.routers.backup import router as backup_router
from attenborough.honeypot.routers.etc import router as etc_router
from attenborough.honeypot.routers.git import router as git_router
from attenborough.honeypot.routers.legacy import router as legacy_router
from attenborough.honeypot.routers.old import router as old_router
from attenborough.honeypot.routers.protected import router as protected_router
from attenborough.honeypot.routers.public import router as public_router

exported_routers = [
    admin_router,
    auth_router,
    backup_router,
    etc_router,
    git_router,
    legacy_router,
    old_router,
    protected_router,
    public_router,
]
