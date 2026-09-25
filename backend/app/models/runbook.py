"""Contracts for runbook documents, versions, and approval state."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RunbookStatus = Literal["draft", "approved", "published"]


class RunbookMetadata(BaseModel):
    """Version and provenance metadata stored with a runbook."""

    version: int = Field(ge=1)
    repository_url: str | None = None
    repository_commit: str | None = None
    provider: Literal["static", "mock"]
    prompt_version: str = "runbook-writer-v1"
    content_hash: str = Field(min_length=64, max_length=64)
    status: RunbookStatus = "draft"
    created_at: datetime
    approved_by: int | None = None
    approved_at: datetime | None = None


class RunbookDraft(BaseModel):
    """A scanned Markdown runbook ready for storage."""

    content: str = Field(min_length=1)
    metadata: RunbookMetadata
