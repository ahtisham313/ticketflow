"""Version 1 API routers."""

from app.api.v1.auth import router as auth_router
from app.api.v1.comments import router as comments_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.tickets import router as tickets_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.ws import router as ws_router

__all__ = [
    "auth_router",
    "comments_router",
    "dashboard_router",
    "tickets_router",
    "webhooks_router",
    "ws_router",
]
