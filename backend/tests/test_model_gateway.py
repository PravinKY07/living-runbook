import pytest

from app.services.model_gateway import (
    GatewayRequest,
    MockProvider,
    ModelGateway,
    ProviderName,
    ProviderUnavailable,
    StaticProvider,
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


def test_static_provider_runs_validated_manifest_analysis():
    request = GatewayRequest(
        task="service_mapper",
        sanitized_content="internal sanitized manifest",
        analysis_input={
            "files": [
                {
                    "path": "app.py",
                    "size_bytes": 60,
                    "sanitized_content": "from fastapi import FastAPI\n\n@app.get('/health')\ndef health():\n    return {}\n",
                }
            ],
            "skipped": [],
            "total_bytes": 60,
            "repository_commit": "abc1234",
        },
    )

    response = ModelGateway().generate(ProviderName.STATIC, request)

    assert response.provider == ProviderName.STATIC
    assert response.output["provider"] == "static"
    assert response.output["service"]["entrypoints"][0]["kind"] == "route"


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


def test_gateway_can_register_a_provider():
    gateway = ModelGateway({ProviderName.STATIC: StaticProvider()})
    gateway.register(MockProvider())

    response = gateway.generate(ProviderName.MOCK, make_request())

    assert response.provider == ProviderName.MOCK
