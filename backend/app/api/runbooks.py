"""Runbook review, approval, publication, and safe Q&A endpoints."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.auth import get_current_user, require_roles
from app.models.runbook import RunbookDraft
from app.models.user import UserRecord
from app.services.runbook_store import (
    RunbookApprovalError,
    RunbookNotFoundError,
    SQLiteRunbookStore,
)

router = APIRouter(prefix="/api/runbooks", tags=["runbooks"])
CurrentUser = Annotated[UserRecord, Depends(get_current_user)]
ApproverUser = Annotated[UserRecord, Depends(require_roles("approver"))]


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AnswerResponse(BaseModel):
    answer: str
    citations: list[str]
    provider: Literal["static"] = "static"


@router.get("/{runbook_id}", response_model=RunbookDraft)
def get_runbook(
    runbook_id: str,
    request: Request,
    _user: CurrentUser,
) -> RunbookDraft:
    """Return the current runbook version."""
    return _get_runbook(request, runbook_id).draft


@router.get("/{runbook_id}/versions", response_model=list[RunbookDraft])
def get_runbook_versions(
    runbook_id: str,
    request: Request,
    _user: CurrentUser,
) -> list[RunbookDraft]:
    """Return stored runbook versions, newest first."""
    try:
        return list(_store(request).list_versions(runbook_id))
    except RunbookNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{runbook_id}/approve", response_model=RunbookDraft)
def approve_runbook(
    runbook_id: str,
    request: Request,
    user: ApproverUser,
) -> RunbookDraft:
    """Approve a draft runbook as an Approver."""
    try:
        return _store(request).approve(
            runbook_id,
            approver_id=user.id,
            role=user.role,
        ).draft
    except RunbookNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RunbookApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/{runbook_id}/publish", response_model=RunbookDraft)
def publish_runbook(
    runbook_id: str,
    request: Request,
    user: ApproverUser,
) -> RunbookDraft:
    """Publish an approved runbook as an Approver."""
    try:
        return _store(request).publish(runbook_id, role=user.role).draft
    except RunbookNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RunbookApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/{runbook_id}/ask", response_model=AnswerResponse)
def ask_runbook(
    runbook_id: str,
    request: Request,
    payload: QuestionRequest,
    _user: CurrentUser,
) -> AnswerResponse:
    """Answer a question from the stored runbook only."""
    draft = _get_runbook(request, runbook_id).draft
    question_terms = {
        term
        for term in re.findall(r"[a-z0-9_]+", payload.question.lower())
        if len(term) > 2
    }
    matches: list[tuple[int, str]] = []
    for line_number, line in enumerate(draft.content.splitlines(), start=1):
        lowered = line.lower()
        if line.strip() and any(term in lowered for term in question_terms):
            matches.append((line_number, line.strip()))

    if not matches:
        return AnswerResponse(
            answer="The current runbook does not contain enough evidence to answer that question.",
            citations=[],
        )

    answer_lines = [f"- {line}" for _, line in matches[:5]]
    return AnswerResponse(
        answer="Relevant entries from the current runbook:\n" + "\n".join(answer_lines),
        citations=[f"runbook:{line_number}" for line_number, _ in matches[:5]],
    )


def _store(request: Request) -> SQLiteRunbookStore:
    return request.app.state.runbook_store


def _get_runbook(request: Request, runbook_id: str):
    try:
        return _store(request).get(runbook_id)
    except RunbookNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
