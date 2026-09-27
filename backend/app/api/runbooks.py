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
    RunbookIntegrityError,
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
    except RunbookIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored runbook content failed its integrity check.",
        ) from exc


@router.post("/{runbook_id}/approve", response_model=RunbookDraft)
def approve_runbook(
    runbook_id: str,
    request: Request,
    user: ApproverUser,
) -> RunbookDraft:
    """Approve a draft runbook as an Approver."""
    try:
        approved = _store(request).approve(
            runbook_id,
            approver_id=user.id,
            role=user.role,
        ).draft
        _record_audit(
            request,
            event_type="runbook_approved",
            outcome="success",
            actor_id=user.id,
            resource_id=runbook_id,
        )
        return approved
    except RunbookNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RunbookApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RunbookIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored runbook content failed its integrity check.",
        ) from exc


@router.post("/{runbook_id}/publish", response_model=RunbookDraft)
def publish_runbook(
    runbook_id: str,
    request: Request,
    user: ApproverUser,
) -> RunbookDraft:
    """Publish an approved runbook as an Approver."""
    try:
        published = _store(request).publish(runbook_id, role=user.role).draft
        _record_audit(
            request,
            event_type="runbook_published",
            outcome="success",
            actor_id=user.id,
            resource_id=runbook_id,
        )
        return published
    except RunbookNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RunbookApprovalError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RunbookIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored runbook content failed its integrity check.",
        ) from exc


@router.post("/{runbook_id}/ask", response_model=AnswerResponse)
def ask_runbook(
    runbook_id: str,
    request: Request,
    payload: QuestionRequest,
    _user: CurrentUser,
) -> AnswerResponse:
    """Answer a question from focused sections of the stored runbook only."""
    if _is_prompt_injection_question(payload.question):
        return AnswerResponse(
            answer=(
                "I can only answer from the sanitized runbook and cannot reveal "
                "hidden instructions or private files."
            ),
            citations=[],
        )
    if _is_sensitive_question(payload.question):
        return AnswerResponse(
            answer="I cannot provide credentials, secrets, or other sensitive values.",
            citations=[],
        )
    if _is_action_request(payload.question):
        return AnswerResponse(
            answer="The application does not execute commands or perform automatic remediation.",
            citations=[],
        )
    draft = _get_runbook(request, runbook_id).draft
    status_answer = _status_answer(payload.question, draft.metadata.status)
    if status_answer is not None:
        return status_answer
    question_terms = _question_terms(payload.question)
    lines = draft.content.splitlines()
    focus_terms = _focus_terms(question_terms)
    if focus_terms:
        candidate_lines = [
            (line_number, line)
            for line_number, line in enumerate(lines, start=1)
            if any(term in line.lower() for term in focus_terms)
        ]
    else:
        section_lines = _matching_section_lines(lines, question_terms)
        candidate_lines = section_lines or [
            (line_number, line)
            for line_number, line in enumerate(lines, start=1)
            if any(term in line.lower() for term in question_terms)
        ]
    matches: list[tuple[int, str]] = []
    seen_text: set[str] = set()
    for line_number, line in candidate_lines:
        cleaned = _clean_runbook_line(line)
        if cleaned and cleaned not in seen_text:
            seen_text.add(cleaned)
            matches.append((line_number, cleaned))
    matches = matches[:5]

    if not matches:
        return AnswerResponse(
            answer="The current runbook does not contain enough evidence to answer that question.",
            citations=[],
        )

    answer_lines = [f"- {line}" for _, line in matches]
    return AnswerResponse(
        answer="Relevant evidence from the current runbook:\n" + "\n".join(answer_lines),
        citations=[f"runbook:{line_number}" for line_number, _ in matches],
    )


def _is_prompt_injection_question(question: str) -> bool:
    """Refuse attempts to override the runbook or reveal hidden context."""
    normalized = question.lower()
    injection_terms = (
        "ignore previous",
        "ignore the runbook",
        "system prompt",
        "developer message",
        "reveal instructions",
        "print the contents",
    )
    if any(term in normalized for term in injection_terms):
        return True
    # Asking about a real .env file is an exfiltration attempt, but the runbook
    # legitimately cites .env.example, so that name stays answerable.
    return ".env" in normalized and ".env.example" not in normalized


def _is_sensitive_question(question: str) -> bool:
    """Prevent Q&A from being used to request credentials or secrets."""
    normalized = question.lower()
    sensitive_terms = ("password", "passwd", "secret", "token", "api key", "apikey", "credential")
    return any(term in normalized for term in sensitive_terms)


def _is_action_request(question: str) -> bool:
    """Prevent Q&A from being used to request executable or remedial actions."""
    normalized = question.lower()
    action_terms = (
        "restart",
        "restarts",
        "restarting",
        "remediate",
        "remediation",
        "execute",
        "run the",
        "deploy this",
        "deploy the",
        "deploy it",
        "automatic deploy",
    )
    return any(term in normalized for term in action_terms)


def _question_terms(question: str) -> set[str]:
    ignored = {
        "and",
        "application",
        "are",
        "detected",
        "does",
        "for",
        "from",
        "how",
        "policy",
        "project",
        "provider",
        "service",
        "the",
        "this",
        "what",
        "were",
        "which",
        "with",
    }
    terms = {
        term
        for term in re.findall(r"[a-z0-9_]+", question.lower())
        if len(term) > 2 and term not in ignored
    }
    if {"times", "timed", "timing"} & terms and "out" in terms:
        terms.add("timeout")
    return terms


def _status_answer(question: str, status: str) -> AnswerResponse | None:
    """Answer approval-status questions from trusted runbook metadata."""
    normalized = question.lower()
    if not any(term in normalized for term in ("approved", "published", "status")):
        return None
    return AnswerResponse(
        answer=f"The current runbook status is {status}.",
        citations=[],
    )


def _focus_terms(question_terms: set[str]) -> set[str]:
    """Return a narrow evidence filter for configuration and dependency questions."""
    if "framework" in question_terms:
        return {"framework"}
    if "commit" in question_terms:
        return {"commit"}
    if "files" in question_terms and "analyzed" in question_terms:
        return {"files"}
    if "database" in question_terms:
        return {"database", "db"}
    if "timeout" in question_terms:
        return {"timeout"}
    if "environment" in question_terms:
        return {"environment"}
    if {"dependency", "dependencies"} & question_terms and {
        "serve",
        "runtime",
    } & question_terms:
        return {"runtime"}
    return set()


def _matching_section_lines(lines: list[str], question_terms: set[str]) -> list[tuple[int, str]]:
    section_terms = {
        "failure": ("failure",),
        "dependency": ("dependency", "dependencies"),
        "dependencies": ("dependency", "dependencies"),
        "configuration": ("configuration", "config"),
        "defined": ("entry point", "entrypoints", "external call"),
        "endpoint": ("entry point", "entrypoints", "external call"),
        "entry": ("entry point", "entrypoints", "external call"),
        "handled": ("entry point", "entrypoints", "external call"),
        "implements": ("entry point", "entrypoints", "external call"),
        "framework": ("service overview", "overview"),
        "health": ("entry point", "entrypoints", "external call"),
        "provenance": ("provenance",),
        "commit": ("provenance",),
        "analyzed": ("provenance",),
    }
    wanted_heading: tuple[str, ...] | None = None
    for term in question_terms:
        for key, headings in section_terms.items():
            if key in term or term in key:
                wanted_heading = headings
                break
        if wanted_heading:
            break
    if wanted_heading is None:
        return []

    matches: list[tuple[int, str]] = []
    in_section = False
    for line_number, line in enumerate(lines, start=1):
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            in_section = any(heading.startswith(candidate) for candidate in wanted_heading)
            continue
        if in_section:
            matches.append((line_number, line))
    return matches


def _clean_runbook_line(line: str) -> str | None:
    text = line.strip()
    if not text or text.startswith(("#", ">", "|", "```")):
        return None
    text = re.sub(r"^[-*]\s+", "", text)
    location = ""
    location_match = re.search(r"\s+—\s+`([^`]+)`\s*$", text)
    if location_match:
        location = f" ({location_match.group(1)})"
        text = text[: location_match.start()].strip()
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text.lower().startswith(
        ("no ", "static analysis cannot prove", "this draft requires")
    ):
        return None
    return f"{text}{location}"


def _store(request: Request) -> SQLiteRunbookStore:
    return request.app.state.runbook_store


def _record_audit(
    request: Request,
    *,
    event_type: str,
    outcome: str,
    actor_id: int | None = None,
    resource_id: str | None = None,
) -> None:
    audit_store = getattr(request.app.state, "audit_store", None)
    if audit_store is not None:
        audit_store.record(
            event_type=event_type,
            outcome=outcome,
            actor_id=actor_id,
            resource_id=resource_id,
        )


def _get_runbook(request: Request, runbook_id: str):
    try:
        return _store(request).get(runbook_id)
    except RunbookNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RunbookIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored runbook content failed its integrity check.",
        ) from exc
