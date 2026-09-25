"""Provider-neutral model gateway.

The MVP uses only local static analysis and deterministic mock output. Keeping
provider selection behind one gateway makes the analysis components independent
of how results are produced.
"""

from collections.abc import Callable
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.models.analysis import AnalysisResult
from app.services.analysis_service import analyze_manifest
from app.services.safe_manifest import SafeFileManifest, manifest_from_dict

MAX_OUTPUT_TOKENS = 4000
MAX_TIMEOUT_SECONDS = 60.0


class ProviderName(str, Enum):
    """Supported provider labels."""

    STATIC = "static"
    MOCK = "mock"


class GatewayRequest(BaseModel):
    """Bounded input sent to a provider."""

    task: str = Field(min_length=1, max_length=100)
    sanitized_content: str = Field(max_length=100_000)
    model_role: str = Field(default="analysis", min_length=1, max_length=50)
    max_output_tokens: int = Field(default=1200, ge=1, le=MAX_OUTPUT_TOKENS)
    timeout_seconds: float = Field(default=15.0, gt=0, le=MAX_TIMEOUT_SECONDS)
    analysis_input: dict[str, Any] | None = None


class ProviderResponse(BaseModel):
    """Structured provider output with an honest provider label."""

    provider: ProviderName
    model_role: str
    output: dict[str, Any]


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot be used safely."""


class ModelProvider(Protocol):
    """Interface implemented by every provider."""

    name: ProviderName

    def generate(self, request: GatewayRequest) -> ProviderResponse:
        """Generate a structured response for a bounded request."""


class StaticProvider:
    """Deterministic local provider used for repository analysis."""

    name = ProviderName.STATIC

    def __init__(
        self,
        analyzer: Callable[[SafeFileManifest], AnalysisResult] = analyze_manifest,
    ) -> None:
        self._analyzer = analyzer

    def generate(self, request: GatewayRequest) -> ProviderResponse:
        if request.analysis_input is not None:
            try:
                manifest = manifest_from_dict(request.analysis_input)
                result = self._analyzer(manifest)
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderUnavailable("Static analysis input is invalid.") from exc
            return ProviderResponse(
                provider=self.name,
                model_role=request.model_role,
                output=result.model_dump(mode="json"),
            )
        return ProviderResponse(
            provider=self.name,
            model_role=request.model_role,
            output={
                "status": "static_analysis_ready",
                "task": request.task,
                "findings": [],
                "note": "Provide a sanitized manifest for repository analysis.",
            },
        )


class MockProvider:
    """Deterministic provider for tests and fallback demonstrations."""

    name = ProviderName.MOCK

    def generate(self, request: GatewayRequest) -> ProviderResponse:
        return ProviderResponse(
            provider=self.name,
            model_role=request.model_role,
            output={
                "task": request.task,
                "findings": [
                    {
                        "id": f"mock-{request.task}",
                        "confidence": "low",
                        "evidence": [],
                    }
                ],
                "note": "Deterministic mock output for tests.",
            },
        )


class ModelGateway:
    """Single entry point for the MVP's static and mock providers."""

    def __init__(self, providers: dict[ProviderName, ModelProvider] | None = None) -> None:
        default_providers: dict[ProviderName, ModelProvider] = {
            ProviderName.STATIC: StaticProvider(),
            ProviderName.MOCK: MockProvider(),
        }
        self._providers = providers or default_providers

    def register(self, provider: ModelProvider) -> None:
        """Register or replace a provider."""
        self._providers[provider.name] = provider

    def generate(self, provider_name: ProviderName, request: GatewayRequest) -> ProviderResponse:
        """Validate limits, select a provider, and return structured output."""
        if request.max_output_tokens > MAX_OUTPUT_TOKENS:
            raise ValueError("max_output_tokens exceeds the gateway limit")
        if request.timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise ValueError("timeout_seconds exceeds the gateway limit")

        provider = self._providers.get(provider_name)
        if provider is None:
            raise ProviderUnavailable(f"Provider '{provider_name.value}' is not registered.")
        return provider.generate(request)
