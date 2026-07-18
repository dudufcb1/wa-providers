from __future__ import annotations

from typing import Any

import pytest

import wa_providers.cloudapi as cloudapi_module
import wa_providers.evolution as evolution_module
from wa_providers import CloudAPIClient, EvolutionClient, get_provider


class StubHTTPClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def request(
        self,
        method: str,
        path: str,
        *,
        retry: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "retry": retry,
                **kwargs,
            }
        )
        return self.response

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_cloudapi_send_text_builds_payload_and_returns_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"messages": [{"id": "wamid.cloud-result"}]})
    constructor_kwargs: dict[str, Any] = {}

    def build_http(**kwargs: Any) -> StubHTTPClient:
        constructor_kwargs.update(kwargs)
        return http

    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", build_http)
    client = CloudAPIClient(
        token="cloud-token",
        phone_number_id="phone-number-id-1",
        graph_version="v22.0",
    )

    result = await client.send_text("5215550000001", "Hola desde Cloud API", preview_url=True)

    assert constructor_kwargs["base_url"] == "https://graph.facebook.com/v22.0"
    assert constructor_kwargs["headers"] == {
        "Authorization": "Bearer cloud-token",
        "Content-Type": "application/json",
    }
    assert http.calls == [
        {
            "method": "POST",
            "path": "/phone-number-id-1/messages",
            "retry": False,
            "json": {
                "messaging_product": "whatsapp",
                "to": "5215550000001",
                "type": "text",
                "text": {
                    "preview_url": True,
                    "body": "Hola desde Cloud API",
                },
            },
        }
    ]
    assert result.provider == "cloudapi"
    assert result.message_id == "wamid.cloud-result"
    assert result.accepted is True

    await client.aclose()
    assert http.closed is True


@pytest.mark.asyncio
async def test_evolution_send_text_builds_payload_and_returns_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"key": {"id": "evolution-result-id"}})
    constructor_kwargs: dict[str, Any] = {}

    def build_http(**kwargs: Any) -> StubHTTPClient:
        constructor_kwargs.update(kwargs)
        return http

    monkeypatch.setattr(evolution_module, "PooledHTTPClient", build_http)
    client = EvolutionClient(
        base_url="https://evolution.example.test/",
        api_key="evolution-key",
        instance="recall-sales",
    )

    result = await client.send_text("5215550000001", "Hola desde Evolution")

    assert constructor_kwargs["base_url"] == "https://evolution.example.test"
    assert constructor_kwargs["headers"] == {
        "apikey": "evolution-key",
        "Content-Type": "application/json",
    }
    assert http.calls == [
        {
            "method": "POST",
            "path": "/message/sendText/recall-sales",
            "retry": False,
            "json": {
                "number": "5215550000001",
                "text": "Hola desde Evolution",
            },
        }
    ]
    assert result.provider == "evolution"
    assert result.message_id == "evolution-result-id"
    assert result.accepted is True

    await client.aclose()
    assert http.closed is True


@pytest.mark.asyncio
async def test_cloudapi_send_template_uses_non_retryable_message_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"messages": [{"id": "wamid.template-result"}]})
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")

    try:
        result = await client.send_template(
            "5215550000001",
            "appointment_reminder",
            lang="es_MX",
            body_params=["Eduardo", 42],
        )

        assert http.calls == [
            {
                "method": "POST",
                "path": "/phone-number-id-1/messages",
                "retry": False,
                "json": {
                    "messaging_product": "whatsapp",
                    "to": "5215550000001",
                    "type": "template",
                    "template": {
                        "name": "appointment_reminder",
                        "language": {"code": "es_MX"},
                        "components": [
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": "Eduardo"},
                                    {"type": "text", "text": "42"},
                                ],
                            }
                        ],
                    },
                },
            }
        ]
        assert result.message_id == "wamid.template-result"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_send_document_uses_non_retryable_message_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"messages": [{"id": "wamid.document-result"}]})
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")

    try:
        result = await client.send_document(
            "5215550000001",
            link="https://files.example.test/document.pdf",
            filename="document.pdf",
            caption="Documento solicitado",
        )

        assert http.calls == [
            {
                "method": "POST",
                "path": "/phone-number-id-1/messages",
                "retry": False,
                "json": {
                    "messaging_product": "whatsapp",
                    "to": "5215550000001",
                    "type": "document",
                    "document": {
                        "link": "https://files.example.test/document.pdf",
                        "filename": "document.pdf",
                        "caption": "Documento solicitado",
                    },
                },
            }
        ]
        assert result.message_id == "wamid.document-result"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_mark_read_uses_explicit_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"success": True})
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")

    try:
        response = await client.mark_read("wamid.inbound-message")

        assert response == {"success": True}
        assert http.calls == [
            {
                "method": "POST",
                "path": "/phone-number-id-1/messages",
                "retry": True,
                "json": {
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": "wamid.inbound-message",
                },
            }
        ]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_evolution_send_document_uses_non_retryable_message_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"key": {"id": "evolution-document-id"}})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    try:
        result = await client.send_document(
            "5215550000001",
            link="https://files.example.test/document.pdf",
            filename="document.pdf",
            caption="Documento solicitado",
        )

        assert http.calls == [
            {
                "method": "POST",
                "path": "/message/sendMedia/recall-sales",
                "retry": False,
                "json": {
                    "number": "5215550000001",
                    "mediatype": "document",
                    "media": "https://files.example.test/document.pdf",
                    "fileName": "document.pdf",
                    "caption": "Documento solicitado",
                },
            }
        ]
        assert result.message_id == "evolution-document-id"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_evolution_set_webhook_uses_explicit_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"configured": True})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    try:
        response = await client.set_webhook(
            "https://api.recall.test/webhooks/evolution",
            events=["MESSAGES_UPSERT"],
        )

        assert response == {"configured": True}
        assert http.calls == [
            {
                "method": "POST",
                "path": "/webhook/set/recall-sales",
                "retry": True,
                "json": {
                    "url": "https://api.recall.test/webhooks/evolution",
                    "webhook_by_events": False,
                    "events": ["MESSAGES_UPSERT"],
                },
            }
        ]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_factory_builds_cloudapi_and_evolution_providers() -> None:
    cloud = get_provider(
        {
            "provider": "CLOUDAPI",
            "token": "cloud-token",
            "phone_number_id": "phone-number-id-1",
            "graph_version": "v22.0",
        }
    )
    evolution = get_provider(
        {
            "provider": "evolution",
            "base_url": "https://evolution.example.test",
            "api_key": "evolution-key",
            "instance": "recall-sales",
        }
    )

    try:
        assert isinstance(cloud, CloudAPIClient)
        assert cloud.phone_number_id == "phone-number-id-1"
        assert isinstance(evolution, EvolutionClient)
        assert evolution.instance == "recall-sales"
    finally:
        await cloud.aclose()
        await evolution.aclose()


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Proveedor de WhatsApp no soportado"):
        get_provider({"provider": "unknown"})
