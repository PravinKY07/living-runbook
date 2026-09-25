"""Tests for GET /api/audit — approver-only audit log endpoint."""

import json
import re

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.audit_store import SQLiteAuditStore
from app.services.demo_seed import seed_demo_users
from app.services.user_store import SQLiteUserStore

# Patterns that must never appear in safe audit responses.
_SECRET_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"api[_\-]?key", re.IGNORECASE),
    re.compile(r"session", re.IGNORECASE),
    re.compile(r"hash", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"traceback", re.IGNORECASE),
    re.compile(r"\\\\"),  # workspace paths (Windows-style)
]


def _make_client(tmp_path) -> tuple[TestClient, SQLiteAuditStore]:
    """Create a test client with seeded users and a shared audit store."""
    settings = Settings(
        session_secret="test-session-secret-that-is-long-enough",
        session_https_only=False,
        database_path=str(tmp_path / "test.db"),
    )
    store = SQLiteUserStore(settings.database_path)
    seed_demo_users(
        store,
        editor_email="editor@example.test",
        editor_password="editor-test-password",
        approver_email="approver@example.test",
        approver_password="approver-test-password",
    )
    audit_store = SQLiteAuditStore(settings.database_path)
    app = create_app(settings=settings, user_store=store)
    # Replace the audit store on app state so we can pre-seed events.
    client = TestClient(app)
    # Seed a few benign events via the shared store instance.
    audit_store.record(
        event_type="login",
        outcome="success",
        actor_id=1,
        resource_id=None,
        metadata={"ip": "127.0.0.1"},
    )
    audit_store.record(
        event_type="runbook.generate",
        outcome="success",
        actor_id=1,
        resource_id="repo-abc",
        metadata={"provider": "static"},
    )
    # Attach to app state so the endpoint sees the same store.
    app.state.audit_store = audit_store
    return client, audit_store


def _login(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---------------------------------------------------------------------------
# Access-control tests
# ---------------------------------------------------------------------------


def test_unauthenticated_returns_401(tmp_path):
    client, _ = _make_client(tmp_path)

    response = client.get("/api/audit")

    assert response.status_code == 401


def test_editor_returns_403(tmp_path):
    client, _ = _make_client(tmp_path)
    _login(client, "editor@example.test", "editor-test-password")

    response = client.get("/api/audit")

    assert response.status_code == 403


def test_approver_receives_audit_events(tmp_path):
    client, _ = _make_client(tmp_path)
    _login(client, "approver@example.test", "approver-test-password")

    response = client.get("/api/audit")

    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) >= 2
    # All required fields present in each event.
    for event in events:
        assert "event_type" in event
        assert "actor_id" in event
        assert "resource_id" in event
        assert "outcome" in event
        assert "created_at" in event
        assert "metadata" in event


def test_approver_sees_correct_event_types(tmp_path):
    client, _ = _make_client(tmp_path)
    _login(client, "approver@example.test", "approver-test-password")

    response = client.get("/api/audit")

    assert response.status_code == 200
    event_types = {e["event_type"] for e in response.json()}
    assert "login" in event_types
    assert "runbook.generate" in event_types


# ---------------------------------------------------------------------------
# Limit enforcement tests
# ---------------------------------------------------------------------------


def test_default_limit_is_100(tmp_path):
    """Endpoint accepts requests without an explicit limit."""
    client, _ = _make_client(tmp_path)
    _login(client, "approver@example.test", "approver-test-password")

    response = client.get("/api/audit")

    assert response.status_code == 200


def test_explicit_limit_respected(tmp_path):
    client, audit_store = _make_client(tmp_path)
    # Add 5 more events so there are at least 7 total.
    for i in range(5):
        audit_store.record(
            event_type=f"extra.event.{i}",
            outcome="success",
            actor_id=None,
            resource_id=None,
            metadata={},
        )
    _login(client, "approver@example.test", "approver-test-password")

    response = client.get("/api/audit?limit=3")

    assert response.status_code == 200
    assert len(response.json()) == 3


def test_limit_above_100_is_rejected(tmp_path):
    """FastAPI should reject limit > 100 with 422 Unprocessable Entity."""
    client, _ = _make_client(tmp_path)
    _login(client, "approver@example.test", "approver-test-password")

    response = client.get("/api/audit?limit=101")

    assert response.status_code == 422


def test_limit_zero_is_rejected(tmp_path):
    """FastAPI should reject limit < 1 with 422 Unprocessable Entity."""
    client, _ = _make_client(tmp_path)
    _login(client, "approver@example.test", "approver-test-password")

    response = client.get("/api/audit?limit=0")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# No-secrets safety test
# ---------------------------------------------------------------------------


def test_response_contains_no_secret_like_values(tmp_path):
    """Audit responses must not contain secret-like field names or values."""
    client, audit_store = _make_client(tmp_path)
    # Record an event that could accidentally carry secret-like keys.
    audit_store.record(
        event_type="user.login",
        outcome="success",
        actor_id=2,
        resource_id=None,
        metadata={"ip": "10.0.0.1", "user_agent": "pytest"},
    )
    _login(client, "approver@example.test", "approver-test-password")

    response = client.get("/api/audit")

    assert response.status_code == 200
    body = response.text
    for pattern in _SECRET_PATTERNS:
        assert not pattern.search(body), (
            f"Forbidden pattern {pattern.pattern!r} found in audit response"
        )


# ---------------------------------------------------------------------------
# list_recent unit tests (store-level, no HTTP)
# ---------------------------------------------------------------------------


def test_list_recent_returns_newest_first(tmp_path):
    store = SQLiteAuditStore(str(tmp_path / "audit.db"))
    store.record(event_type="first", outcome="ok", metadata={})
    store.record(event_type="second", outcome="ok", metadata={})
    store.record(event_type="third", outcome="ok", metadata={})

    events = store.list_recent(limit=3)

    assert len(events) == 3
    assert events[0]["event_type"] == "third"
    assert events[1]["event_type"] == "second"
    assert events[2]["event_type"] == "first"


def test_list_recent_caps_at_100(tmp_path):
    store = SQLiteAuditStore(str(tmp_path / "audit.db"))
    for i in range(5):
        store.record(event_type=f"evt.{i}", outcome="ok", metadata={})

    # Even when the store has fewer rows, limit is honoured.
    events = store.list_recent(limit=200)
    assert len(events) == 5  # only 5 exist; 200 was silently capped to 100


def test_list_recent_default_limit_is_100(tmp_path):
    store = SQLiteAuditStore(str(tmp_path / "audit.db"))
    # Inserting 3 events; default limit of 100 returns all 3.
    for i in range(3):
        store.record(event_type=f"evt.{i}", outcome="ok", metadata={})

    events = store.list_recent()
    assert len(events) == 3


def test_oversized_metadata_is_replaced_with_valid_safe_json(tmp_path):
    store = SQLiteAuditStore(str(tmp_path / "audit.db"))
    store.record(
        event_type="large.event",
        outcome="success",
        metadata={"value": "x" * 3000},
    )

    event = store.list_recent(limit=1)[0]

    assert json.loads(event["metadata_json"]) == {"truncated": True}


def test_list_recent_row_has_expected_keys(tmp_path):
    store = SQLiteAuditStore(str(tmp_path / "audit.db"))
    store.record(
        event_type="test.event",
        outcome="success",
        actor_id=42,
        resource_id="res-1",
        metadata={"key": "value"},
    )

    events = store.list_recent(limit=1)

    assert len(events) == 1
    row = events[0]
    assert row["event_type"] == "test.event"
    assert row["outcome"] == "success"
    assert row["actor_id"] == 42
    assert row["resource_id"] == "res-1"
    assert "metadata_json" in row
    assert "created_at" in row
