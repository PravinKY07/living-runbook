"""Repository analysis submission endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.api.auth import require_roles
from app.models.jobs import AnalysisJob
from app.models.user import UserRecord

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


class AnalyzeRepositoryRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=2048)


EditorOrApprover = Annotated[UserRecord, Depends(require_roles("editor", "approver"))]


@router.post(
    "/analyze",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_repository(
    request: Request,
    payload: AnalyzeRepositoryRequest,
    _user: EditorOrApprover,
) -> AnalysisJob:
    """Queue a safe static analysis job for a public GitHub repository."""
    return request.app.state.job_manager.submit(payload.repository_url)
