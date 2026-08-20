"""Common API error response contracts."""

from pydantic import BaseModel, ConfigDict


class ValidationErrorDetail(BaseModel):
    """One safe, client-readable request validation failure."""

    model_config = ConfigDict(extra="forbid")

    field: str
    message: str


class ErrorBody(BaseModel):
    """Stable machine and human-readable fields for an API error."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: list[ValidationErrorDetail] | None = None


class ErrorResponse(BaseModel):
    """Envelope returned for API exceptions and validation failures."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody
