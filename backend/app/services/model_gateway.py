"""Provider-neutral model gateway.

All model providers must be called through this module. The gateway keeps
provider selection, safe limits, and output labeling in one place.
"""

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.config import Settings

MAX_OUTPUT_TOKENS = 4000
MAX_TIMEOUT_SECONDS = 60.0


class ProviderName(str, Enum):
    """Supported provider labels."""

    STATIC = "static"
    MOCK = "mock"
    WATSONX = "watsonx"


class GatewayRequest(BaseModel):
    """Bounded input sent to a model provider."""

    task: str = Field(min_length=1, max_length=100)
    sanitized_content: str = Field(max_length=100_000)
    model_role: str = Field(default="analysis", min_length=1, max_length=50)
    max_output_tokens: int = Field(default=1200, ge=1, le=MAX_OUTPUT_TOKENS)
    timeout_seconds: float = Field(default=15.0, gt=0, le=MAX_TIMEOUT_SECONDS)


class ProviderResponse(BaseModel):
    """Structured provider output with an honest provider label."""

    provider: ProviderName
    model_role: str
    output: dict[str, Any]


class PreflightResult(BaseModel):
    """Safe preflight result that never contains credentials."""

    provider: ProviderName
    ready: bool
    missing_settings: list[str]
    message: str


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot be used safely."""


class ModelProvider(Protocol):
    """Interface implemented by every provider."""

    name: ProviderName

    def generate(self, request: GatewayRequest) -> ProviderResponse:
        """Generate a structured response for a bounded request."""


class StaticProvider:
    """Deterministic local provider used when external models are unavailable."""

    name = ProviderName.STATIC

    def generate(self, request: GatewayRequest) -> ProviderResponse:
        return ProviderResponse(
            provider=self.name,
            model_role=request.model_role,
            output={
                "status": "static_analysis_ready",
                "task": request.task,
                "findings": [],
                "note": "Static analyzer modules are added in Phase 3.",
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


class WatsonxProvider:
    """Configuration-aware watsonx.ai provider stub.

    Network inference is intentionally not implemented in this checkpoint.
    The preflight only reports whether configuration is present; it never logs
    or returns credential values.
    """

    name = ProviderName.WATSONX

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def preflight(self) -> PreflightResult:
        required = {
            "WATSONX_APIKEY": self._settings.watsonx_apikey,
            "WATSONX_PROJECT_ID": self._settings.watsonx_project_id,
            "WATSONX_URL": self._settings.watsonx_url,
            "CODE_ANALYSIS_MODEL": self._settings.code_analysis_model,
            "WRITER_MODEL": self._settings.writer_model,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            return PreflightResult(
                provider=self.name,
                ready=False,
                missing_settings=missing,
                message="Watsonx configuration is incomplete.",
            )
        return PreflightResult(
            provider=self.name,
            ready=True,
            missing_settings=[],
            message="Watsonx configuration fields are present; network preflight is not implemented yet.",
        )

    def generate(self, request: GatewayRequest) -> ProviderResponse:
        result = self.preflight()
        if not result.ready:
            raise ProviderUnavailable(result.message)
        raise ProviderUnavailable(
            "Watsonx network inference is not enabled in this checkpoint."
        )


class ModelGateway:
    """Single entry point for model providers."""

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
