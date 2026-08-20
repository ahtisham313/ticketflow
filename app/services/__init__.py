"""Application business services."""

from app.services.auth_service import (
    AuthenticationError,
    DuplicateEmailError,
    issue_access_token_from_refresh,
    login_user,
    register_customer,
)
from app.services.comment_service import create_comment, list_comments
from app.services.cache_service import invalidate_ticket_caches
from app.services.dashboard_service import calculate_dashboard_stats
from app.services.ws_manager import connection_manager
from app.services.webhook_service import (
    WebhookNotFoundError,
    create_webhook_registration,
    deactivate_webhook_registration,
    list_webhook_deliveries,
    list_webhook_registrations,
    schedule_webhook_event,
)
from app.services.ticket_service import (
    TicketNotFoundError,
    TicketStateError,
    change_ticket_status,
    create_ticket,
    delete_open_ticket,
    get_accessible_ticket,
    list_tickets,
    update_open_ticket,
)

__all__ = [
    "AuthenticationError",
    "DuplicateEmailError",
    "issue_access_token_from_refresh",
    "login_user",
    "register_customer",
    "create_comment",
    "list_comments",
    "invalidate_ticket_caches",
    "calculate_dashboard_stats",
    "connection_manager",
    "WebhookNotFoundError",
    "create_webhook_registration",
    "deactivate_webhook_registration",
    "list_webhook_deliveries",
    "list_webhook_registrations",
    "schedule_webhook_event",
    "TicketNotFoundError",
    "TicketStateError",
    "change_ticket_status",
    "create_ticket",
    "delete_open_ticket",
    "get_accessible_ticket",
    "list_tickets",
    "update_open_ticket",
]
