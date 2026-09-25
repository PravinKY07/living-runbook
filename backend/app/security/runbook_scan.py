"""Final secret scan for generated Markdown runbooks."""

from dataclasses import dataclass

from app.security.redaction import contains_secret_like_value


class UnsafeRunbookError(ValueError):
    """Raised when generated Markdown still contains secret-like values."""


@dataclass(frozen=True, slots=True)
class RunbookScanResult:
    """Safe result of the final Markdown scan."""

    safe: bool
    reason: str | None = None


def scan_runbook(markdown: str) -> RunbookScanResult:
    """Reject a runbook if common secret patterns remain."""
    if contains_secret_like_value(markdown):
        return RunbookScanResult(
            safe=False,
            reason="Secret-like value detected in generated Markdown.",
        )
    return RunbookScanResult(safe=True)


def require_safe_runbook(markdown: str) -> None:
    """Raise when a runbook cannot be stored or published."""
    result = scan_runbook(markdown)
    if not result.safe:
        raise UnsafeRunbookError(result.reason or "Unsafe runbook content.")
