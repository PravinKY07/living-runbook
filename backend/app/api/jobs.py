"""Analysis job status endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.auth import get_current_user
from app.models.jobs import AnalysisJob
from app.models.user import UserRecord
from app.services.job_store import JobNotFoundError

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
CurrentUser = Annotated[UserRecord, Depends(get_current_user)]


@router.get("/{job_id}", response_model=AnalysisJob)
def get_job(request: Request, job_id: str, _user: CurrentUser) -> AnalysisJob:
    """Return safe progress and result metadata for an analysis job."""
    try:
        return request.app.state.job_manager.get(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
