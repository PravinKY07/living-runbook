"""Contracts for persisted analysis jobs."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "completed", "failed"]


class AnalysisJob(BaseModel):
    """Safe job status exposed to the API and frontend."""

    id: str = Field(min_length=1)
    repository_url: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    runbook_id: str | None = None
    error_message: str | None = None
