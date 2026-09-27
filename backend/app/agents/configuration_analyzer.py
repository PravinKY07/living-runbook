"""Static Configuration Analyzer."""

from __future__ import annotations

import re

from app.agents.common import evidence_for
from app.models.analysis import ConfigurationAnalysis, ConfigurationFinding, Finding
from app.services.safe_manifest import SafeFileManifest

_ENV_PATTERNS = (
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"os\.environ\.get\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)"),
)
# A bare module-level constant such as MAX_ATTEMPTS = 3 is not an environment
# variable. Reporting it as one is a false claim, so it is classified separately.
_CONSTANT_PATTERN = re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*=", re.MULTILINE)
_TIMEOUT_PATTERN = re.compile(r"\b(timeout|connect_timeout|read_timeout|request_timeout)\b", re.IGNORECASE)
_DATABASE_PATTERN = re.compile(r"\b(DATABASE_URL|DB_HOST|DB_PORT|POSTGRES|SQLALCHEMY)\b", re.IGNORECASE)
_LOGGING_PATTERN = re.compile(r"\b(logging|logger|LOG_LEVEL)\b", re.IGNORECASE)
_FLAG_PATTERN = re.compile(r"\b(debug|feature|enabled|ENVIRONMENT)\b", re.IGNORECASE)


def analyze_configuration(manifest: SafeFileManifest) -> ConfigurationAnalysis:
    """Find configuration references without exposing their values."""
    settings: list[ConfigurationFinding] = []
    findings: list[Finding] = []
    seen: set[tuple[str, str, str, int]] = set()

    for item in manifest.files:
        for line_number, line in enumerate(item.sanitized_content.splitlines(), start=1):
            names: list[tuple[str, str]] = []
            for pattern in _ENV_PATTERNS:
                names.extend((match.group(1), "environment") for match in pattern.finditer(line))
            if _TIMEOUT_PATTERN.search(line):
                names.append(("timeout", "timeout"))
            if _DATABASE_PATTERN.search(line):
                names.append(("database", "database"))
            if _LOGGING_PATTERN.search(line):
                names.append(("logging", "logging"))
            if _FLAG_PATTERN.search(line):
                names.append(("feature_flag", "flag"))

            # A name already read from the environment is an environment
            # variable even when the same line also assigns a default.
            already_named = {name for name, _ in names}
            for match in _CONSTANT_PATTERN.finditer(line):
                if match.group(1) not in already_named:
                    names.append((match.group(1), "constant"))

            for name, kind in names:
                key = (name, kind, item.path, line_number)
                if key in seen:
                    continue
                seen.add(key)
                evidence = evidence_for(item, line_number)
                settings.append(
                    ConfigurationFinding(
                        name=name,
                        value_summary=None,
                        kind=kind,
                        evidence=evidence,
                    )
                )
                findings.append(
                    Finding(
                        kind="configuration",
                        summary=f"Configuration reference detected: {name}.",
                        evidence=[evidence],
                        confidence="medium",
                    )
                )

    return ConfigurationAnalysis(settings=settings, findings=findings)
