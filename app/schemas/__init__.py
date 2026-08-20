"""Pydantic request and response schemas."""

from app.schemas.auth import (
    AccessTokenResponse,
    CurrentUserResponse,
    LoginRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserRegisterRequest,
)
from app.schemas.comment import CommentCreateRequest, CommentResponse
from app.schemas.dashboard import (
    DashboardStatsResponse,
    TicketCategoryCounts,
    TicketPriorityCounts,
    TicketStatusCounts,
)
from app.schemas.ticket import (
    TicketCreateRequest,
    TicketListResponse,
    TicketResponse,
    TicketStatusUpdateRequest,
    TicketUpdateRequest,
)

__all__ = [
    "AccessTokenResponse",
    "CurrentUserResponse",
    "LoginRequest",
    "RefreshTokenRequest",
    "TokenPairResponse",
    "UserRegisterRequest",
    "CommentCreateRequest",
    "CommentResponse",
    "DashboardStatsResponse",
    "TicketCategoryCounts",
    "TicketPriorityCounts",
    "TicketStatusCounts",
    "TicketCreateRequest",
    "TicketListResponse",
    "TicketResponse",
    "TicketStatusUpdateRequest",
    "TicketUpdateRequest",
]
