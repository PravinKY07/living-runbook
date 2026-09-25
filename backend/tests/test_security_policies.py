import pytest

from app.security.file_policy import (
    FileLimits,
    FilePolicyError,
    is_allowed_file,
    validate_file_entry,
)
from app.security.redaction import (
    REDACTED_CREDENTIALS,
    REDACTED_EMAIL,
    REDACTED_PRIVATE_KEY,
    REDACTED_SECRET,
    REDACTED_TOKEN,
    contains_secret_like_value,
    redact_text,
)
from app.security.url_policy import (
    URLPolicyError,
    is_public_ip,
    validate_github_repository_url,
    validate_public_hostname,
    validate_redirect_url,
)


def test_valid_github_repository_url_is_normalized():
    repository = validate_github_repository_url("https://github.com/example/project.git")

    assert repository.owner == "example"
    assert repository.name == "project"
    assert repository.normalized_url == "https://github.com/example/project"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/project",
        "https://gitlab.com/example/project",
        "https://user:password@github.com/example/project",
        "https://github.com/example/project?tab=readme",
        "https://github.com/example/project/extra",
        "file:///C:/repo",
        "https://127.0.0.1/example/project",
    ],
)
def test_invalid_repository_urls_are_rejected(url):
    with pytest.raises(URLPolicyError):
        validate_github_repository_url(url)


def test_public_and_private_ip_classification():
    assert is_public_ip("8.8.8.8") is True
    assert is_public_ip("127.0.0.1") is False
    assert is_public_ip("10.0.0.1") is False
    assert is_public_ip("169.254.169.254") is False
    assert is_public_ip("not-an-ip") is False


def test_hostname_with_private_resolution_is_rejected():
    with pytest.raises(URLPolicyError):
        validate_public_hostname("github.com", resolver=lambda _: ["127.0.0.1"])


def test_redirect_host_allowlist_and_dns_check():
    with pytest.raises(URLPolicyError):
        validate_redirect_url(
            "https://evil.example/file.zip",
            resolver=lambda _: ["8.8.8.8"],
        )

    validate_redirect_url(
        "https://codeload.github.com/example/project/zip/main",
        resolver=lambda _: ["8.8.8.8"],
    )


def test_safe_file_allowlist():
    assert is_allowed_file("app.py") is True
    assert is_allowed_file("config.yaml") is True
    assert is_allowed_file(".env.example") is True
    assert is_allowed_file("Dockerfile") is True
    assert is_allowed_file(".env") is False
    assert is_allowed_file("private.pem") is False
    assert is_allowed_file("../outside.py") is False
    assert is_allowed_file("node_modules/package/index.js") is False


def test_file_entry_limits():
    assert validate_file_entry("app.py", 100) == "app.py"

    with pytest.raises(FilePolicyError):
        validate_file_entry("app.py", 600_000, FileLimits(max_file_bytes=500_000))

    with pytest.raises(FilePolicyError):
        validate_file_entry("../app.py", 100)


def test_redacts_common_secret_patterns():
    text = (
        "API_KEY=abc123\n"
        "Authorization: Bearer abcdefghijklmnop\n"
        "DATABASE_URL=postgres://user:password@example.invalid/db\n"
        "contact: person@example.com\n"
        "-----BEGIN PRIVATE KEY-----\nprivate material\n-----END PRIVATE KEY-----"
    )

    redacted = redact_text(text)

    assert "abc123" not in redacted
    assert "abcdefghijklmnop" not in redacted
    assert "password" not in redacted
    assert "person@example.com" not in redacted
    assert "private material" not in redacted
    assert REDACTED_SECRET in redacted
    assert REDACTED_TOKEN in redacted
    assert REDACTED_CREDENTIALS in redacted
    assert REDACTED_EMAIL in redacted
    assert REDACTED_PRIVATE_KEY in redacted


def test_redaction_leaves_ordinary_text_unchanged():
    text = "GET /api/health returns status ok after the database check."

    assert redact_text(text) == text
    assert contains_secret_like_value(text) is False
