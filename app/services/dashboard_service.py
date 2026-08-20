"""PostgreSQL aggregate calculations for the agent dashboard."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.schemas.dashboard import (
    DashboardStatsResponse,
    TicketCategoryCounts,
    TicketPriorityCounts,
    TicketStatusCounts,
)


async def calculate_dashboard_stats(session: AsyncSession) -> DashboardStatsResponse:
    """Calculate current counts using database aggregate/group-by queries."""

    total = int(await session.scalar(select(func.count(Ticket.id))) or 0)

    status_counts = {member.value: 0 for member in TicketStatus}
    status_rows = await session.execute(
        select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
    )
    for ticket_status, count in status_rows:
        status_counts[ticket_status.value] = int(count)

    priority_counts = {member.value: 0 for member in TicketPriority}
    priority_rows = await session.execute(
        select(Ticket.priority, func.count(Ticket.id)).group_by(Ticket.priority)
    )
    for priority, count in priority_rows:
        priority_counts[priority.value] = int(count)

    category_counts = {member.value: 0 for member in TicketCategory}
    category_rows = await session.execute(
        select(Ticket.category, func.count(Ticket.id)).group_by(Ticket.category)
    )
    for category, count in category_rows:
        category_counts[category.value] = int(count)

    return DashboardStatsResponse(
        total=total,
        by_status=TicketStatusCounts(**status_counts),
        by_priority=TicketPriorityCounts(**priority_counts),
        by_category=TicketCategoryCounts(**category_counts),
    )
