from typing import Annotated

from fastapi import Depends
from fastapi.testclient import TestClient

from app.api.auth import require_roles
from app.config import Settings
from app.main import create_app
from app.models.user import UserRecord
from app.services.demo_seed import seed_demo_users
from app.services.user_store import SQLiteUserStore


def make_client(tmp_path, role: str = "editor") -> TestClient:
    settings = Settings(
        session_secret="test-session-secret-that-is-long-enough",
        session_https_only=False,
        database_path=str(tmp_path / "auth.db"),
    )
    store = SQLiteUserStore(settings.database_path)
    seed_demo_users(
        store,
        editor_email="editor@example.test",
        editor_password="editor-test-password",
        approver_email="approver@example.test",
        approver_password="approver-test-password",
    )
    app = create_app(settings=settings, user_store=store)

    ApproverOnly = Annotated[UserRecord, Depends(require_roles("approver"))]

    @app.get("/test/approver-only")
    def approver_only(user: ApproverOnly):
        return {"role": user.role}

    return TestClient(app)


def login(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_sets_httponly_session_cookie(tmp_path):
    client = make_client(tmp_path)

    response = login(client, "editor@example.test", "editor-test-password")

    assert response.status_code == 200
    assert response.json()["role"] == "editor"
    assert "httponly" in response.headers["set-cookie"].lower()


def test_me_returns_authenticated_user(tmp_path):
    client = make_client(tmp_path)
    login(client, "editor@example.test", "editor-test-password")

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "editor@example.test"


def test_wrong_password_is_rejected(tmp_path):
    client = make_client(tmp_path)

    response = login(client, "editor@example.test", "wrong-password")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_logout_requires_login_again(tmp_path):
    client = make_client(tmp_path)
    login(client, "editor@example.test", "editor-test-password")

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_editor_cannot_access_approver_route(tmp_path):
    client = make_client(tmp_path)
    login(client, "editor@example.test", "editor-test-password")

    response = client.get("/test/approver-only")

    assert response.status_code == 403


def test_approver_can_access_approver_route(tmp_path):
    client = make_client(tmp_path)
    login(client, "approver@example.test", "approver-test-password")

    response = client.get("/test/approver-only")

    assert response.status_code == 200
    assert response.json() == {"role": "approver"}


def test_auth_is_unavailable_without_session_secret(tmp_path):
    settings = Settings(
        database_path=str(tmp_path / "auth.db"),
    )
    store = SQLiteUserStore(settings.database_path)
    client = TestClient(create_app(settings=settings, user_store=store))

    response = login(client, "editor@example.test", "any-password")

    assert response.status_code == 503
