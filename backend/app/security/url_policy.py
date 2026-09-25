"""Public GitHub URL validation and SSRF protection."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

GITHUB_HOST = "github.com"
ALLOWED_REDIRECT_HOSTS = {
    "github.com",
    "api.github.com",
    "codeload.github.com",
    "raw.githubusercontent.com",
}
_OWNER_OR_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+$")


class URLPolicyError(ValueError):
    """Raised when a URL is not allowed by the repository URL policy."""


@dataclass(frozen=True, slots=True)
class GitHubRepository:
    """Validated public GitHub repository coordinates."""

    owner: str
    name: str
    normalized_url: str


def validate_github_repository_url(url: str) -> GitHubRepository:
    """Validate an HTTPS GitHub repository root URL."""
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise URLPolicyError("Repository URL is missing or too long.")
    if any(character.isspace() for character in url) or "\\" in url or "%" in url:
        raise URLPolicyError("Repository URL contains unsafe characters.")

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise URLPolicyError("Repository URL is malformed.") from exc

    if parsed.scheme.lower() != "https":
        raise URLPolicyError("Only HTTPS GitHub URLs are allowed.")
    if parsed.username or parsed.password:
        raise URLPolicyError("Repository URLs cannot contain credentials.")
    if parsed.hostname is None or parsed.hostname.lower() != GITHUB_HOST:
        raise URLPolicyError("Only github.com repository URLs are allowed.")
    if port not in (None, 443):
        raise URLPolicyError("Only the HTTPS port is allowed.")
    if parsed.query or parsed.fragment:
        raise URLPolicyError("Query strings and fragments are not allowed.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 2:
        raise URLPolicyError("URL must point to a GitHub repository root.")
    owner, repository = path_parts
    repository = repository.removesuffix(".git")
    if not owner or not repository:
        raise URLPolicyError("Repository owner and name are required.")
    if owner in {".", ".."} or repository in {".", ".."}:
        raise URLPolicyError("Repository path traversal is not allowed.")
    if not _OWNER_OR_REPOSITORY.fullmatch(owner) or not _OWNER_OR_REPOSITORY.fullmatch(repository):
        raise URLPolicyError("Repository owner or name contains invalid characters.")

    return GitHubRepository(
        owner=owner,
        name=repository,
        normalized_url=f"https://{GITHUB_HOST}/{owner}/{repository}",
    )


def is_public_ip(address: str) -> bool:
    """Return whether an IP address is globally routable."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not any(
        (
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )


def _resolve_hostname(hostname: str) -> list[str]:
    infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def validate_public_hostname(
    hostname: str,
    resolver: Callable[[str], list[str]] = _resolve_hostname,
) -> None:
    """Reject hostnames that resolve to any non-public address."""
    if not hostname:
        raise URLPolicyError("Hostname is required.")
    addresses = resolver(hostname)
    if not addresses:
        raise URLPolicyError("Hostname did not resolve.")
    if any(not is_public_ip(address) for address in addresses):
        raise URLPolicyError("Hostname resolves to a private or reserved address.")


def validate_redirect_url(
    url: str,
    resolver: Callable[[str], list[str]] = _resolve_hostname,
) -> None:
    """Validate a redirect from the controlled GitHub download allowlist."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise URLPolicyError("Redirect URL is malformed.") from exc

    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if parsed.scheme.lower() != "https" or hostname not in ALLOWED_REDIRECT_HOSTS:
        raise URLPolicyError("Redirect host is not allowed.")
    if parsed.username or parsed.password or port not in (None, 443):
        raise URLPolicyError("Redirect URL contains unsafe network settings.")
    validate_public_hostname(hostname, resolver=resolver)
