"""Agent dashboard statistics response contracts."""

from pydantic import BaseModel, ConfigDict, Field


class TicketStatusCounts(BaseModel):
    """Stable counts for every ticket status."""

    model_config = ConfigDict(extra="forbid")

    OPEN: int = Field(default=0, ge=0)
    IN_PROGRESS: int = Field(default=0, ge=0)
    RESOLVED: int = Field(default=0, ge=0)
    CLOSED: int = Field(default=0, ge=0)


class TicketPriorityCounts(BaseModel):
    """Stable counts for every ticket priority."""

    model_config = ConfigDict(extra="forbid")

    LOW: int = Field(default=0, ge=0)
    MEDIUM: int = Field(default=0, ge=0)
    HIGH: int = Field(default=0, ge=0)


class TicketCategoryCounts(BaseModel):
    """Stable counts for every ticket category."""

    model_config = ConfigDict(extra="forbid")

    BILLING: int = Field(default=0, ge=0)
    TECHNICAL: int = Field(default=0, ge=0)
    GENERAL: int = Field(default=0, ge=0)


class DashboardStatsResponse(BaseModel):
    """Current PostgreSQL-backed ticket distribution statistics."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    by_status: TicketStatusCounts
    by_priority: TicketPriorityCounts
    by_category: TicketCategoryCounts
