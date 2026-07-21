from __future__ import annotations

from typing import Any

import httpx
import pytest

import wa_providers.cloudapi as cloudapi_module
import wa_providers.evolution as evolution_module
from wa_providers import CloudAPIClient, EvolutionClient, ProviderTransportError, get_provider
from wa_providers.capabilities import (
    CloudMediaDownloader,
    EvolutionMediaDownloader,
    GenericMediaSender,
    HealthChecker,
    InteractiveSender,
    ReadMarker,
    TemplateSender,
    TextSender,
    WebhookConfigurator,
)
from wa_providers.http import BinaryResponse


class StubHTTPClient:
    def __init__(
        self,
        response: dict[str, Any],
        binary_response: BinaryResponse | None = None,
    ) -> None:
        self.response = response
        self.binary_response = binary_response
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

    async def request_bytes(
        self,
        method: str,
        path: str,
        *,
        retry: bool | None = None,
        **kwargs: Any,
    ) -> BinaryResponse:
        self.calls.append(
            {
                "method": method,
                "path": path,
                "retry": retry,
                "binary": True,
                **kwargs,
            }
        )
        if self.binary_response is None:
            raise AssertionError("No se configuro una respuesta binaria")
        return self.binary_response

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
            by_events=True,
            include_base64=True,
            headers={"x-webhook-secret": "secret"},
        )

        assert response == {"configured": True}
        assert http.calls == [
            {
                "method": "POST",
                "path": "/webhook/set/recall-sales",
                "retry": True,
                "json": {
                    "webhook": {
                        "enabled": True,
                        "url": "https://api.recall.test/webhooks/evolution",
                        "byEvents": True,
                        "base64": True,
                        "events": ["MESSAGES_UPSERT"],
                        "headers": {"x-webhook-secret": "secret"},
                    }
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


@pytest.mark.asyncio
async def test_clients_expose_provider_capabilities() -> None:
    cloud = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")
    evolution = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )
    try:
        assert isinstance(cloud, TextSender)
        assert isinstance(cloud, TemplateSender)
        assert isinstance(cloud, InteractiveSender)
        assert isinstance(cloud, CloudMediaDownloader)
        assert isinstance(cloud, ReadMarker)
        assert isinstance(cloud, HealthChecker)
        assert not isinstance(cloud, GenericMediaSender)
        assert not isinstance(cloud, WebhookConfigurator)
        assert isinstance(evolution, TextSender)
        assert isinstance(evolution, GenericMediaSender)
        assert isinstance(evolution, EvolutionMediaDownloader)
        assert isinstance(evolution, WebhookConfigurator)
        assert not isinstance(evolution, InteractiveSender)
        assert not isinstance(evolution, ReadMarker)
        assert not isinstance(evolution, HealthChecker)
    finally:
        await cloud.aclose()
        await evolution.aclose()


@pytest.mark.asyncio
async def test_cloudapi_send_list_applies_wire_limits_without_altering_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"messages": [{"id": "wamid.list-result"}]})
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")
    rows = [
        {
            "id": f"row-id-{index}-" + "x" * 40,
            "title": "T" * 30,
            "description": "D" * 80,
        }
        for index in range(12)
    ]

    try:
        result = await client.send_list(
            "5215550000001",
            "Elige una opcion",
            "B" * 30,
            rows,
            header="H" * 70,
        )

        assert result.message_id == "wamid.list-result"
        assert result.accepted is True
        call = http.calls[0]
        assert call["method"] == "POST"
        assert call["path"] == "/phone-number-id-1/messages"
        assert call["retry"] is False
        interactive = call["json"]["interactive"]
        sent_rows = interactive["action"]["sections"][0]["rows"]
        assert len(sent_rows) == 10
        assert [row["id"] for row in sent_rows] == [row["id"] for row in rows[:10]]
        assert all(row["title"] == "T" * 23 + "…" for row in sent_rows)
        assert all(row["description"] == "D" * 71 + "…" for row in sent_rows)
        assert interactive["action"]["button"] == "B" * 19 + "…"
        assert interactive["header"]["text"] == "H" * 59 + "…"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_send_buttons_applies_wire_limits_without_altering_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"messages": [{"id": "wamid.buttons-result"}]})
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")
    buttons = [{"id": f"button-id-{index}-" + "x" * 40, "title": "T" * 30} for index in range(5)]

    try:
        result = await client.send_buttons("5215550000001", "Elige", buttons)

        assert result.message_id == "wamid.buttons-result"
        call = http.calls[0]
        assert call["retry"] is False
        sent_buttons = call["json"]["interactive"]["action"]["buttons"]
        assert len(sent_buttons) == 3
        assert [button["reply"]["id"] for button in sent_buttons] == [
            button["id"] for button in buttons[:3]
        ]
        assert all(button["reply"]["title"] == "T" * 19 + "…" for button in sent_buttons)
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("method", "args", "error_match"),
    [
        ("send_list", ("5215550000001", "body", "Ver", []), "rows"),
        ("send_list", ("5215550000001", "body", "Ver", [{"id": "", "title": "A"}]), "id"),
        ("send_list", ("5215550000001", "body", "Ver", [{"id": "a", "title": ""}]), "title"),
        ("send_buttons", ("5215550000001", "body", []), "buttons"),
        ("send_buttons", ("5215550000001", "", [{"id": "a", "title": "A"}]), "body"),
    ],
)
@pytest.mark.asyncio
async def test_cloudapi_interactive_rejects_empty_required_values(
    method: str,
    args: tuple[Any, ...],
    error_match: str,
) -> None:
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")
    try:
        with pytest.raises(ValueError, match=error_match):
            await getattr(client, method)(*args)
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("method", "args", "error_match"),
    [
        (
            "send_list",
            ("5215550000001", "body", "Ver", [{"id": "x" * 201, "title": "A"}]),
            "200",
        ),
        (
            "send_buttons",
            ("5215550000001", "body", [{"id": "x" * 257, "title": "A"}]),
            "256",
        ),
    ],
)
@pytest.mark.asyncio
async def test_cloudapi_interactive_rejects_oversized_ids_without_altering_them(
    method: str,
    args: tuple[Any, ...],
    error_match: str,
) -> None:
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")
    try:
        with pytest.raises(ValueError, match=error_match):
            await getattr(client, method)(*args)
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("method", "args", "error_match"),
    [
        (
            "send_list",
            (
                "5215550000001",
                "body",
                "Ver",
                [{"id": "duplicate", "title": "A"}, {"id": "duplicate", "title": "B"}],
            ),
            "unicos",
        ),
        (
            "send_buttons",
            (
                "5215550000001",
                "body",
                [{"id": " duplicate", "title": "A"}],
            ),
            "espacios",
        ),
    ],
)
@pytest.mark.asyncio
async def test_cloudapi_interactive_rejects_ambiguous_ids(
    method: str,
    args: tuple[Any, ...],
    error_match: str,
) -> None:
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")
    try:
        with pytest.raises(ValueError, match=error_match):
            await getattr(client, method)(*args)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_interactive_truncates_body_to_wire_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"messages": [{"id": "wamid.buttons-result"}]})
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")
    try:
        await client.send_buttons(
            "5215550000001",
            "B" * 1030,
            [{"id": "continue", "title": "Continuar"}],
        )

        body = http.calls[0]["json"]["interactive"]["body"]["text"]
        assert len(body) == 1024
        assert body == "B" * 1023 + "…"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_get_media_downloads_signed_url_with_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = {
        "url": "https://lookaside.example.test/media-token",
        "mime_type": "application/pdf",
        "filename": "document.pdf",
        "file_size": 3,
    }
    http = StubHTTPClient(
        metadata,
        BinaryResponse(content=b"PDF", headers=httpx.Headers({"content-type": "application/pdf"})),
    )
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")

    try:
        downloaded = await client.get_media("media-id-1")

        assert downloaded.provider == "cloudapi"
        assert downloaded.content == b"PDF"
        assert downloaded.base64 is None
        assert downloaded.mime_type == "application/pdf"
        assert downloaded.filename == "document.pdf"
        assert downloaded.raw == metadata
        assert http.calls == [
            {
                "method": "GET",
                "path": "/media-id-1",
                "retry": None,
                "params": {"phone_number_id": "phone-number-id-1"},
            },
            {
                "method": "GET",
                "path": "https://lookaside.example.test/media-token",
                "retry": None,
                "binary": True,
                "headers": {"Authorization": "Bearer cloud-token"},
            },
        ]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_get_media_rejects_metadata_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"mime_type": "image/jpeg"})
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")
    try:
        with pytest.raises(ProviderTransportError, match="URL") as error:
            await client.get_media("media-id-1")
        assert error.value.body == {"mime_type": "image/jpeg"}
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_evolution_send_media_omits_optional_none_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"key": {"id": "evolution-media-id"}})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    try:
        result = await client.send_media(
            "5215550000001",
            "https://files.example.test/photo.jpg",
            media_type="image",
            mime_type="image/jpeg",
        )

        assert result.message_id == "evolution-media-id"
        assert http.calls == [
            {
                "method": "POST",
                "path": "/message/sendMedia/recall-sales",
                "retry": False,
                "json": {
                    "number": "5215550000001",
                    "mediatype": "image",
                    "media": "https://files.example.test/photo.jpg",
                    "mimetype": "image/jpeg",
                },
            }
        ]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_evolution_get_media_base64_accepts_key_only_and_disables_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = {
        "base64": "UERG",
        "mimetype": "application/pdf",
        "fileName": "document.pdf",
    }
    http = StubHTTPClient(response)
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )
    message = {"key": {"id": "message-id-1"}}

    try:
        downloaded = await client.get_media_base64(message, convert_to_mp4=True)

        assert downloaded.provider == "evolution"
        assert downloaded.content is None
        assert downloaded.base64 == "UERG"
        assert downloaded.mime_type == "application/pdf"
        assert downloaded.filename == "document.pdf"
        assert http.calls == [
            {
                "method": "POST",
                "path": "/chat/getBase64FromMediaMessage/recall-sales",
                "retry": False,
                "json": {"message": message, "convertToMp4": True},
            }
        ]
        with pytest.raises(ValueError, match="key.id"):
            await client.get_media_base64({"key": {}})
        with pytest.raises(TypeError, match="objeto"):
            await client.get_media_base64("message-id-1")  # type: ignore[arg-type]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_evolution_get_media_base64_rejects_missing_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"mimetype": "application/pdf"})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )
    try:
        with pytest.raises(ProviderTransportError, match="base64") as error:
            await client.get_media_base64(
                {"key": {"id": "message-id-1"}, "message": {"documentMessage": {}}}
            )
        assert error.value.body == {"mimetype": "application/pdf"}
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_evolution_send_without_message_id_is_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"status": "PENDING"})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    async with client:
        result = await client.send_text("5215550000001", "Hola")

    assert result.message_id is None
    assert result.accepted is False


@pytest.mark.anyio
async def test_evolution_send_media_rejects_unknown_media_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"key": {"id": "evolution-media-id"}})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    async with client:
        with pytest.raises(ValueError, match="media_type invalido"):
            await client.send_media(
                "5215550000001",
                "https://cdn.test/file.pdf",
                media_type="documento",
            )

    assert http.calls == []


@pytest.mark.anyio
async def test_evolution_creates_an_instance_asking_for_its_qr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"instance": {"instanceName": "linea-ventas"}, "qrcode": {"base64": "..."}})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    async with client:
        await client.create_instance("linea-ventas")

    assert http.calls[0]["path"] == "/instance/create"
    assert http.calls[0]["json"] == {
        "instanceName": "linea-ventas",
        "integration": "WHATSAPP-BAILEYS",
        "qrcode": True,
    }


@pytest.mark.anyio
async def test_evolution_reads_the_connection_state(monkeypatch: pytest.MonkeyPatch) -> None:
    http = StubHTTPClient({"instance": {"instanceName": "linea-ventas", "state": "open"}})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    async with client:
        estado = await client.connection_state("linea-ventas")

    assert estado == "open"
    assert http.calls[0]["path"] == "/instance/connectionState/linea-ventas"


@pytest.mark.anyio
async def test_evolution_instance_operations_default_to_the_configured_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = StubHTTPClient({"instance": {"state": "close"}})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    async with client:
        await client.connect()

    assert http.calls[0]["path"] == "/instance/connect/recall-sales"


@pytest.mark.anyio
async def test_evolution_can_point_the_webhook_at_another_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Al dar de alta un numero hay que configurarle su webhook, no el del cliente."""
    http = StubHTTPClient({"webhook": {"enabled": True}})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    async with client:
        await client.set_webhook("https://mi-app.test/hook", instance_name="linea-ventas")

    assert http.calls[0]["path"] == "/webhook/set/linea-ventas"


@pytest.mark.anyio
async def test_evolution_client_manages_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    from wa_providers.capabilities import InstanceManager

    monkeypatch.setattr(
        evolution_module,
        "PooledHTTPClient",
        lambda **_kwargs: StubHTTPClient({}),
    )
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    async with client:
        assert isinstance(client, InstanceManager)
