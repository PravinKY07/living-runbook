"""Structured contracts for static repository analysis."""

from typing import Literal

from pydantic import BaseModel, Field

ProviderLabel = Literal["static", "mock"]


class Evidence(BaseModel):
    """A validated source reference."""

    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    excerpt: str | None = None


class Finding(BaseModel):
    """One evidence-backed analysis finding."""

    kind: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=500)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    recommendation: str | None = Field(default=None, max_length=500)


class ServiceAnalysis(BaseModel):
    """Service structure discovered by the Service Mapper."""

    service_name: str | None = None
    purpose: str | None = None
    purpose_evidence: Evidence | None = None
    language: str | None = None
    framework: str | None = None
    entrypoints: list[Finding] = Field(default_factory=list)
    external_calls: list[Finding] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class FailureAnalysis(BaseModel):
    """Failure-handling paths discovered by the Failure Analyzer."""

    failure_modes: list[Finding] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class Dependency(BaseModel):
    """A dependency discovered from a manifest or container file."""

    name: str = Field(min_length=1, max_length=200)
    version: str | None = None
    category: Literal["runtime", "development", "data-store", "external-service", "build", "unknown"] = "unknown"
    evidence: Evidence


class DependencyAnalysis(BaseModel):
    """Dependency inventory discovered by the Dependency Mapper."""

    dependencies: list[Dependency] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class ConfigurationFinding(BaseModel):
    """A configuration variable or setting discovered in source."""

    name: str = Field(min_length=1, max_length=200)
    value_summary: str | None = None
    kind: Literal["environment", "timeout", "database", "logging", "flag", "other"]
    evidence: Evidence


class ConfigurationAnalysis(BaseModel):
    """Configuration inventory discovered by the Configuration Analyzer."""

    settings: list[ConfigurationFinding] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Combined structured result for one repository manifest."""

    provider: ProviderLabel
    repository_url: str | None = None
    repository_commit: str | None = None
    files_analyzed: int = Field(ge=0)
    service: ServiceAnalysis
    failures: FailureAnalysis
    dependencies: DependencyAnalysis
    configuration: ConfigurationAnalysis
