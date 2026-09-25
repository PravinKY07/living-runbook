"""Audit log read endpoint — approver role only."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.auth import require_roles
from app.models.user import UserRecord
from app.services.audit_store import SQLiteAuditStore

router = APIRouter(prefix="/api/audit", tags=["audit"])

_MAX_LIMIT = 100

ApproverUser = Annotated[UserRecord, Depends(require_roles("approver"))]


class AuditEventResponse(BaseModel):
    """Safe projection of a stored audit event.

    Fields excluded: raw repository content, passwords, password hashes,
    API keys, session cookies, stack traces, workspace paths.
    """

    event_type: str
    actor_id: int | None
    resource_id: str | None
    outcome: str
    metadata: dict
    created_at: str


def _store(request: Request) -> SQLiteAuditStore:
    return request.app.state.audit_store


@router.get("", response_model=list[AuditEventResponse])
def list_audit_events(
    request: Request,
    _user: ApproverUser,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _MAX_LIMIT,
) -> list[AuditEventResponse]:
    """Return the most recent audit events, newest first.

    Only the ``approver`` role may access this endpoint.
    ``limit`` is capped at 100.
    """
    rows = _store(request).list_recent(limit)
    return [
        AuditEventResponse(
            event_type=row["event_type"],
            actor_id=row["actor_id"],
            resource_id=row["resource_id"],
            outcome=row["outcome"],
            metadata=json.loads(row["metadata_json"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]
