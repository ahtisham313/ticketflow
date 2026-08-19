"""Version 1 API routers."""

from app.api.v1.auth import router as auth_router
from app.api.v1.comments import router as comments_router
from app.api.v1.tickets import router as tickets_router

__all__ = ["auth_router", "comments_router", "tickets_router"]
