"""Static Service Mapper."""

from __future__ import annotations

import ast

from app.agents.common import finding, is_test_path, parse_python, python_files
from app.models.analysis import Finding, ServiceAnalysis
from app.services.safe_manifest import SafeFileManifest

_ROUTE_NAMES = {"delete", "get", "head", "options", "patch", "post", "put", "websocket"}
_EXTERNAL_ROOTS = {"aiohttp", "boto3", "httpx", "requests", "socket", "urllib"}


def analyze_services(manifest: SafeFileManifest) -> ServiceAnalysis:
    """Find service entry points and external calls without executing code."""
    entrypoints: list[Finding] = []
    external_calls: list[Finding] = []
    findings: list[Finding] = []
    frameworks: set[str] = set()
    service_name: str | None = None
    python_found = False

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

    framework = ", ".join(sorted(frameworks)) if frameworks else None
    return ServiceAnalysis(
        service_name=service_name,
        purpose=None,
        language="Python" if python_found else None,
        framework=framework,
        entrypoints=entrypoints,
        external_calls=external_calls,
        findings=findings,
    )


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
