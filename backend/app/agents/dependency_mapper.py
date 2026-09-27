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


def _locate_line(item: ManifestFile, needle: str) -> int | None:
    """Return the 1-based line that really contains ``needle``.

    JSON and TOML carry no line numbers, so the only honest citation is the
    line the literal actually appears on. When it cannot be found (escaped
    characters, multi-line strings) the caller omits the dependency rather
    than inventing a citation.
    """
    if not needle:
        return None
    for line_number, line in enumerate(item.sanitized_content.splitlines(), start=1):
        if needle in line:
            return line_number
    return None


def _dependency_from_requirement(
    item: ManifestFile,
    requirement: str,
    category: str,
) -> Dependency | None:
    """Build a properly cited dependency, or None when it cannot be cited."""
    match = _REQUIREMENT_PATTERN.match(requirement.strip())
    if not match:
        return None
    name, version = match.groups()
    line = _locate_line(item, requirement.strip()) or _locate_line(item, name)
    if line is None:
        return None
    return Dependency(
        name=name,
        version=version or None,
        category=category,
        evidence=evidence_for(item, line),
    )


def _pyproject(item: ManifestFile) -> list[Dependency]:
    try:
        data = tomllib.loads(item.sanitized_content)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []

    dependencies: list[Dependency] = []
    project = data.get("project")
    if not isinstance(project, dict):
        return dependencies

    declared = project.get("dependencies")
    if isinstance(declared, list):
        for requirement in declared:
            if not isinstance(requirement, str):
                continue
            dependency = _dependency_from_requirement(item, requirement, "runtime")
            if dependency is not None:
                dependencies.append(dependency)

    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group, requirements in optional.items():
            # A malformed manifest (a string where a list belongs) must not
            # crash analysis; skip it instead of guessing at its shape.
            if not isinstance(requirements, list):
                continue
            category = "development" if group in {"dev", "test", "lint"} else "unknown"
            for requirement in requirements:
                if not isinstance(requirement, str):
                    continue
                dependency = _dependency_from_requirement(item, requirement, category)
                if dependency is not None:
                    dependencies.append(dependency)
    return dependencies


def _package_json(item: ManifestFile) -> list[Dependency]:
    try:
        data = json.loads(item.sanitized_content)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []

    dependencies: list[Dependency] = []
    for section, category in (("dependencies", "runtime"), ("devDependencies", "development")):
        entries = data.get(section)
        # "dependencies": [] and "dependencies": "react" are both valid JSON
        # and both must be ignored rather than crashing the analysis.
        if not isinstance(entries, dict):
            continue
        for name, version in entries.items():
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            line = _locate_line(item, f'"{name}"')
            if line is None:
                continue
            dependencies.append(
                Dependency(
                    name=name,
                    version=version,
                    category=category,
                    evidence=evidence_for(item, line),
                )
            )
    return dependencies


def _stage_alias(arguments: str) -> str | None:
    """Return the build-stage name in a ``FROM ... AS name`` instruction."""
    parts = arguments.split()
    for index, part in enumerate(parts):
        if part.upper() == "AS" and index + 1 < len(parts):
            return parts[index + 1].lower()
    return None


def _dockerfile(item: ManifestFile) -> list[Dependency]:
    dependencies: list[Dependency] = []
    stages: set[str] = set()
    for line_number, line in enumerate(item.sanitized_content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.upper().startswith("FROM "):
            continue
        parts = stripped.split()
        # Skip build flags such as --platform=... to reach the image reference.
        tokens = [part for part in parts[1:] if not part.startswith("--")]
        if not tokens:
            continue
        image = tokens[0]
        alias = _stage_alias(" ".join(parts[1:]))
        if alias is not None:
            stages.add(alias)
        # A later stage copies from an earlier stage, not from a registry image.
        if image.lower() in stages or "$" in image:
            continue
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
