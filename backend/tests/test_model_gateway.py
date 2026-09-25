import pytest

from app.config import Settings
from app.services.model_gateway import (
    GatewayRequest,
    MockProvider,
    ModelGateway,
    ProviderName,
    ProviderUnavailable,
    StaticProvider,
    WatsonxProvider,
)


def make_request() -> GatewayRequest:
    return GatewayRequest(
        task="service_mapper",
        sanitized_content="sanitized repository content",
        model_role="analysis",
    )


def test_static_provider_is_labeled_static():
    response = ModelGateway().generate(ProviderName.STATIC, make_request())

    assert response.provider == ProviderName.STATIC
    assert response.output["status"] == "static_analysis_ready"


def test_mock_provider_is_labeled_mock():
    response = ModelGateway().generate(ProviderName.MOCK, make_request())

    assert response.provider == ProviderName.MOCK
    assert response.output["findings"][0]["confidence"] == "low"


def test_gateway_rejects_unknown_provider():
    gateway = ModelGateway()
    gateway._providers.pop(ProviderName.MOCK)

    with pytest.raises(ProviderUnavailable):
        gateway.generate(ProviderName.MOCK, make_request())


def test_gateway_enforces_token_limit():
    with pytest.raises(ValueError):
        GatewayRequest(
            task="service_mapper",
            sanitized_content="sanitized repository content",
            max_output_tokens=5000,
        )


def test_watsonx_preflight_reports_missing_settings_without_values():
    provider = WatsonxProvider(Settings(_env_file=None))

    result = provider.preflight()

    assert result.provider == ProviderName.WATSONX
    assert result.ready is False
    assert "WATSONX_APIKEY" in result.missing_settings
    assert "WATSONX_PROJECT_ID" in result.missing_settings
    assert "WRITER_MODEL" in result.missing_settings
    assert "WATSONX_APIKEY" not in result.message


def test_watsonx_preflight_does_not_enable_network_inference():
    settings = Settings(
        watsonx_apikey="test-key-not-real",
        watsonx_project_id="test-project",
        watsonx_url="https://example.invalid",
        code_analysis_model="test-model",
        writer_model="test-writer-model",
    )
    provider = WatsonxProvider(settings)

    result = provider.preflight()

    assert result.ready is True
    with pytest.raises(ProviderUnavailable):
        provider.generate(make_request())


def test_gateway_can_register_a_provider():
    gateway = ModelGateway({ProviderName.STATIC: StaticProvider()})
    gateway.register(MockProvider())

    response = gateway.generate(ProviderName.MOCK, make_request())

    assert response.provider == ProviderName.MOCK
