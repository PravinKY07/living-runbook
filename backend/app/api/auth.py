"""Authentication endpoints and role dependencies."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRecord
from app.security.passwords import verify_password
from app.services.user_store import SQLiteUserStore

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str


def _get_store(request: Request) -> SQLiteUserStore:
    return request.app.state.user_store


def _require_session_configured(request: Request) -> None:
    if not request.app.state.settings.session_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        )


def get_current_user(request: Request) -> UserRecord:
    """Load the current user from the signed session cookie."""
    _require_session_configured(request)
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    user = _get_store(request).get_by_id(user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user


def require_roles(*allowed_roles: str) -> Callable:
    """Return a dependency that allows only the listed roles."""
    allowed = set(allowed_roles)

    def role_dependency(
        user: Annotated[UserRecord, Depends(get_current_user)],
    ) -> UserRecord:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return role_dependency


@router.post("/login", response_model=UserResponse)
def login(request: Request, payload: LoginRequest) -> UserResponse:
    """Authenticate a user and create an HTTP-only session cookie."""
    _require_session_configured(request)
    user = _get_store(request).get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    request.session["user_id"] = user.id
    return UserResponse(id=user.id, email=user.email, role=user.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> None:
    """Clear the current session cookie."""
    _require_session_configured(request)
    request.session.clear()
    response.delete_cookie("session")


CurrentUser = Annotated[UserRecord, Depends(get_current_user)]


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse(id=user.id, email=user.email, role=user.role)
