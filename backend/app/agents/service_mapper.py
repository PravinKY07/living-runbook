"""Static Service Mapper."""

from __future__ import annotations

import ast
import re

from app.agents.common import (
    evidence_for,
    finding,
    is_test_path,
    parse_python,
    python_files,
)
from app.models.analysis import Evidence, Finding, ServiceAnalysis
from app.services.safe_manifest import ManifestFile, SafeFileManifest

_ROUTE_NAMES = {"delete", "get", "head", "options", "patch", "post", "put", "websocket"}
_EXTERNAL_ROOTS = {"aiohttp", "boto3", "httpx", "requests", "socket", "urllib"}
_PURPOSE_LIMIT = 200


def analyze_services(manifest: SafeFileManifest) -> ServiceAnalysis:
    """Find service entry points and external calls without executing code."""
    entrypoints: list[Finding] = []
    external_calls: list[Finding] = []
    findings: list[Finding] = []
    frameworks: set[str] = set()
    service_name: str | None = None
    python_found = False
    purpose_candidates: list[tuple[bool, str, ManifestFile, int]] = []

    for item in python_files(manifest):
        python_found = True
        if is_test_path(item.path):
            continue
        tree = parse_python(item)
        if tree is None:
            findings.append(
                finding(
                    kind="parse_error",
                    summary=f"Could not parse {item.path} as Python.",
                    item=item,
                    line=1,
                    confidence="low",
                )
            )
            continue

        route_in_file = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_route(node):
                    route_finding = finding(
                        kind="route",
                        summary=f"Route handler: {node.name}.",
                        item=item,
                        line=node.lineno,
                        confidence="high",
                    )
                    entrypoints.append(route_finding)
                    findings.append(route_finding)
                    route_in_file = True
            elif isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                root_name = call_name.split(".", 1)[0]
                if root_name in _EXTERNAL_ROOTS:
                    call_finding = finding(
                        kind="external_call",
                        summary=f"External call candidate: {call_name}.",
                        item=item,
                        line=node.lineno,
                        confidence="medium",
                    )
                    external_calls.append(call_finding)
                    findings.append(call_finding)
                if call_name == "FastAPI" and service_name is None:
                    service_name = _string_keyword(node, "title")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in {"fastapi", "flask", "django"}:
                        frameworks.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_name = node.module.split(".", 1)[0]
                if root_name in {"fastapi", "flask", "django"}:
                    frameworks.add(root_name)

        docstring = _module_docstring(tree)
        if docstring is not None:
            text, docstring_line = docstring
            purpose_candidates.append((route_in_file, text, item, docstring_line))

    framework = ", ".join(sorted(frameworks)) if frameworks else None
    purpose, purpose_evidence = _select_purpose(purpose_candidates)
    return ServiceAnalysis(
        service_name=service_name,
        purpose=purpose,
        purpose_evidence=purpose_evidence,
        language="Python" if python_found else None,
        framework=framework,
        entrypoints=entrypoints,
        external_calls=external_calls,
        findings=findings,
    )


def _module_docstring(tree: ast.Module) -> tuple[str, int] | None:
    """Return a module docstring condensed to one summary sentence, with its line.

    Only a literal docstring already present in the source is used. Nothing is
    inferred, so the value can always be traced back to a cited line.
    """
    if not tree.body:
        return None
    first = tree.body[0]
    if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
        return None
    if not isinstance(first.value.value, str):
        return None
    text = " ".join(first.value.value.split())
    if not text:
        return None
    return _condense(text), first.value.lineno


def _condense(text: str) -> str:
    """Reduce a docstring to its leading sentence, cut on a word boundary."""
    summary = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(summary) <= _PURPOSE_LIMIT:
        return summary
    return f"{summary[:_PURPOSE_LIMIT].rsplit(' ', 1)[0]}..."


def _select_purpose(
    candidates: list[tuple[bool, str, ManifestFile, int]],
) -> tuple[str | None, Evidence | None]:
    """Prefer the docstring of a module that also defines route handlers."""
    if not candidates:
        return None, None
    for has_route, text, item, line in candidates:
        if has_route:
            return text, evidence_for(item, line)
    _, text, item, line = candidates[0]
    return text, evidence_for(item, line)


def _is_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_decorator_name(decorator) in _ROUTE_NAMES for decorator in node.decorator_list)


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _string_keyword(node: ast.Call, keyword_name: str) -> str | None:
    for keyword in node.keywords:
        if (
            keyword.arg == keyword_name
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
        ):
            return keyword.value.value
    return None
