"""Static Dependency Mapper."""

from __future__ import annotations

import json
import re
import tomllib

from app.agents.common import evidence_for
from app.models.analysis import Dependency, DependencyAnalysis, Finding
from app.services.safe_manifest import ManifestFile, SafeFileManifest

_REQUIREMENT_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*(.*)$")
_GO_REQUIRE_PATTERN = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s+(v[^\s]+)")
_CARGO_SECTION_PATTERN = re.compile(r"^\[dependencies\]$")
_CARGO_DEPENDENCY_PATTERN = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(.+)$")


def analyze_dependencies(manifest: SafeFileManifest) -> DependencyAnalysis:
    """Read dependency manifests as data, without installing anything."""
    dependencies: list[Dependency] = []
    findings: list[Finding] = []

    for item in manifest.files:
        if item.path.endswith("requirements.txt"):
            dependencies.extend(_requirements(item))
        elif item.path == "pyproject.toml":
            dependencies.extend(_pyproject(item))
        elif item.path == "package.json":
            dependencies.extend(_package_json(item))
        elif item.path == "Dockerfile":
            dependencies.extend(_dockerfile(item))
        elif item.path == "go.mod":
            dependencies.extend(_go_mod(item))
        elif item.path == "Cargo.toml":
            dependencies.extend(_cargo(item))

    unique: dict[tuple[str, str], Dependency] = {}
    for dependency in dependencies:
        key = (dependency.name, dependency.evidence.file)
        unique.setdefault(key, dependency)
    return DependencyAnalysis(dependencies=list(unique.values()), findings=findings)


def _requirements(item: ManifestFile) -> list[Dependency]:
    dependencies: list[Dependency] = []
    for line_number, line in enumerate(item.sanitized_content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        match = _REQUIREMENT_PATTERN.match(stripped)
        if not match:
            continue
        name, version = match.groups()
        dependencies.append(
            Dependency(
                name=name,
                version=version or None,
                category="runtime",
                evidence=evidence_for(item, line_number),
            )
        )
    return dependencies


def _pyproject(item: ManifestFile) -> list[Dependency]:
    try:
        data = tomllib.loads(item.sanitized_content)
    except (tomllib.TOMLDecodeError, ValueError):
        return []

    dependencies: list[Dependency] = []
    project = data.get("project", {})
    for line_number, requirement in enumerate(project.get("dependencies", []), start=1):
        if isinstance(requirement, str):
            match = _REQUIREMENT_PATTERN.match(requirement)
            if match:
                name, version = match.groups()
                dependencies.append(
                    Dependency(
                        name=name,
                        version=version or None,
                        category="runtime",
                        evidence=evidence_for(item, line_number),
                    )
                )
    for group, requirements in data.get("project", {}).get("optional-dependencies", {}).items():
        category = "development" if group in {"dev", "test", "lint"} else "unknown"
        for line_number, requirement in enumerate(requirements, start=1):
            if isinstance(requirement, str):
                match = _REQUIREMENT_PATTERN.match(requirement)
                if match:
                    name, version = match.groups()
                    dependencies.append(
                        Dependency(
                            name=name,
                            version=version or None,
                            category=category,
                            evidence=evidence_for(item, line_number),
                        )
                    )
    return dependencies


def _package_json(item: ManifestFile) -> list[Dependency]:
    try:
        data = json.loads(item.sanitized_content)
    except (json.JSONDecodeError, TypeError):
        return []

    dependencies: list[Dependency] = []
    for section, category in (("dependencies", "runtime"), ("devDependencies", "development")):
        for line_number, (name, version) in enumerate(data.get(section, {}).items(), start=1):
            if isinstance(version, str):
                dependencies.append(
                    Dependency(
                        name=name,
                        version=version,
                        category=category,
                        evidence=evidence_for(item, line_number),
                    )
                )
    return dependencies


def _dockerfile(item: ManifestFile) -> list[Dependency]:
    dependencies: list[Dependency] = []
    for line_number, line in enumerate(item.sanitized_content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.upper().startswith("FROM "):
            continue
        image = stripped.split(None, 1)[1].split()[0]
        dependencies.append(
            Dependency(
                name=image,
                category="build",
                evidence=evidence_for(item, line_number),
            )
        )
    return dependencies


def _go_mod(item: ManifestFile) -> list[Dependency]:
    dependencies: list[Dependency] = []
    in_require_block = False
    for line_number, line in enumerate(item.sanitized_content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block and stripped == ")":
            in_require_block = False
            continue
        candidate = stripped if in_require_block else stripped.removeprefix("require ")
        match = _GO_REQUIRE_PATTERN.match(candidate)
        if match:
            name, version = match.groups()
            dependencies.append(
                Dependency(
                    name=name,
                    version=version,
                    category="runtime",
                    evidence=evidence_for(item, line_number),
                )
            )
    return dependencies


def _cargo(item: ManifestFile) -> list[Dependency]:
    dependencies: list[Dependency] = []
    in_dependencies = False
    for line_number, line in enumerate(item.sanitized_content.splitlines(), start=1):
        stripped = line.strip()
        if _CARGO_SECTION_PATTERN.match(stripped):
            in_dependencies = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_dependencies = False
            continue
        if not in_dependencies:
            continue
        match = _CARGO_DEPENDENCY_PATTERN.match(stripped)
        if match:
            name, version = match.groups()
            dependencies.append(
                Dependency(
                    name=name,
                    version=version.strip('"'),
                    category="runtime",
                    evidence=evidence_for(item, line_number),
                )
            )
    return dependencies
