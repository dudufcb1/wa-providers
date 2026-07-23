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
    TemplateCatalog,
    TemplateSender,
    TextSender,
    VoiceNoteSender,
    WebhookConfigurator,
)
from wa_providers.http import BinaryResponse
from wa_providers.schemas import TemplateCategory, TemplateStatus


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


class SequenceHTTPClient(StubHTTPClient):
    """Stub que devuelve una respuesta distinta por llamada, para probar paginacion."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        super().__init__({})
        self.responses = responses

    async def request(
        self,
        method: str,
        path: str,
        *,
        retry: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        await super().request(method, path, retry=retry, **kwargs)
        if not self.responses:
            raise AssertionError("Se pidieron mas paginas de las configuradas")
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_cloudapi_list_templates_normalizes_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El catalogo crudo de Graph API se aplana al modelo Template del paquete.

    Cubre lo que necesita una pantalla para ofrecer una plantilla: su estado en
    minusculas, su categoria, el texto del cuerpo y las variables que hay que
    llenar antes de enviarla."""
    http = StubHTTPClient(
        {
            "data": [
                {
                    "id": "1667192013751005",
                    "name": "recordatorio_cita",
                    "language": "es_MX",
                    "status": "APPROVED",
                    "category": "UTILITY",
                    "components": [
                        {"type": "HEADER", "format": "TEXT", "text": "Tu cita"},
                        {
                            "type": "BODY",
                            "text": "Hola {{1}}, te esperamos el {{2}}. Gracias {{1}}.",
                        },
                    ],
                }
            ],
            "paging": {"cursors": {"before": "MAZDZD", "after": "MjQZD"}},
        }
    )
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(
        token="cloud-token",
        phone_number_id="phone-number-id-1",
        waba_id="waba-1",
    )

    try:
        templates = await client.list_templates(status="APPROVED")

        assert http.calls == [
            {
                "method": "GET",
                "path": "/waba-1/message_templates",
                "retry": True,
                "params": {"limit": 100, "status": "APPROVED"},
            }
        ]
        assert len(templates) == 1
        template = templates[0]
        assert template.provider == "cloudapi"
        assert template.name == "recordatorio_cita"
        assert template.language == "es_MX"
        assert template.status is TemplateStatus.APPROVED
        assert template.category is TemplateCategory.UTILITY
        assert template.is_sendable is True
        assert template.body == "Hola {{1}}, te esperamos el {{2}}. Gracias {{1}}."
        # La variable repetida se pide una sola vez y el orden es el del envio.
        assert template.variables == ["1", "2"]
        assert len(template.components) == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_list_templates_follows_cursor_until_last_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con varias paginas se sigue el cursor `after` y se para en la ultima.

    Graph API manda `cursors.after` incluso en la ultima pagina; lo que dice que
    aun hay mas es `paging.next`. Sin esa distincion el recorrido se cicla."""
    http = SequenceHTTPClient(
        [
            {
                "data": [{"name": "uno", "language": "es_MX", "status": "APPROVED"}],
                "paging": {"cursors": {"after": "cursor-1"}, "next": "https://graph/next"},
            },
            {
                "data": [{"name": "dos", "language": "es_MX", "status": "PENDING"}],
                "paging": {"cursors": {"after": "cursor-2"}},
            },
        ]
    )
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(
        token="cloud-token",
        phone_number_id="phone-number-id-1",
        waba_id="waba-1",
    )

    try:
        templates = await client.list_templates(limit=1)

        assert [call["params"] for call in http.calls] == [
            {"limit": 1},
            {"limit": 1, "after": "cursor-1"},
        ]
        assert [t.name for t in templates] == ["uno", "dos"]
        assert templates[1].status is TemplateStatus.PENDING
        assert templates[1].is_sendable is False
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_list_templates_survives_unknown_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un estado que Meta agregue despues no debe tumbar la lectura del catalogo.

    Cae a UNKNOWN y la plantilla se sigue listando, en vez de reventar la pantalla
    completa por un valor nuevo."""
    http = StubHTTPClient(
        {"data": [{"name": "nueva", "language": "es_MX", "status": "SOMETHING_NEW"}]}
    )
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(
        token="cloud-token",
        phone_number_id="phone-number-id-1",
        waba_id="waba-1",
    )

    try:
        templates = await client.list_templates()

        assert templates[0].status is TemplateStatus.UNKNOWN
        assert templates[0].category is TemplateCategory.UNKNOWN
        assert templates[0].variables == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cloudapi_list_templates_requires_waba_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin WABA ID no hay catalogo que consultar: falla claro y no llama a Meta.

    El cliente se puede construir solo para enviar (ahi basta el phone_number_id),
    asi que el error tiene que salir al pedir plantillas, no al construirlo."""
    http = StubHTTPClient({})
    monkeypatch.setattr(cloudapi_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = CloudAPIClient(token="cloud-token", phone_number_id="phone-number-id-1")

    try:
        with pytest.raises(ValueError, match="waba_id"):
            await client.list_templates()
        assert http.calls == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_only_cloudapi_exposes_the_template_catalog() -> None:
    """El catalogo es capacidad de Cloud API; Evolution no la implementa.

    En WhatsApp no oficial no hay plantillas que aprobar, asi que quien consuma
    el paquete debe poder preguntarlo en runtime antes de ofrecer la pantalla."""
    cloud = CloudAPIClient(
        token="cloud-token",
        phone_number_id="phone-number-id-1",
        waba_id="waba-1",
    )
    evolution = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )
    try:
        assert isinstance(cloud, TemplateCatalog)
        assert not isinstance(evolution, TemplateCatalog)
    finally:
        await cloud.aclose()
        await evolution.aclose()


def test_phone_from_jid_keeps_raw_digits_and_ignores_lid() -> None:
    """Del JID solo se saca la parte del numero, sin normalizar y sin los @lid.

    Normalizar es del consumidor (cada sistema machea con su formato); los JID
    `@lid` son identificadores internos de WhatsApp, no telefonos."""
    from wa_providers.evolution import _phone_from_jid

    assert _phone_from_jid("5215512345678@s.whatsapp.net") == "5215512345678"
    assert _phone_from_jid("99999999@lid") is None
    assert _phone_from_jid("sin-arroba") is None
    assert _phone_from_jid(None) is None


def test_first_instance_record_handles_list_and_wrapped() -> None:
    """fetchInstances puede venir como lista, envuelto en {'instance':...} o plano.

    La forma cambia entre versiones de Evolution, asi que la lectura no puede
    asumir una sola."""
    from wa_providers.evolution import _first_instance_record

    assert _first_instance_record([{"ownerJid": "x"}]) == {"ownerJid": "x"}
    assert _first_instance_record({"instance": {"ownerJid": "y"}}) == {"ownerJid": "y"}
    assert _first_instance_record({"ownerJid": "z"}) == {"ownerJid": "z"}
    assert _first_instance_record("nope") is None


@pytest.mark.asyncio
async def test_evolution_fetch_profile_reads_owner_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Devuelve el numero y el nombre de perfil de la instancia ya vinculada.

    Es lo que deja mostrar '5215512345678 - Ventas' en vez del nombre interno de
    la instancia."""
    import json

    body = json.dumps(
        [{"ownerJid": "5215512345678@s.whatsapp.net", "profileName": "Ventas"}]
    ).encode()
    http = StubHTTPClient(
        {},
        binary_response=BinaryResponse(content=body, headers=httpx.Headers({})),
    )
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="ghl-x",
    )

    try:
        profile = await client.fetch_profile("ghl-x")

        assert http.calls == [
            {
                "method": "GET",
                "path": "/instance/fetchInstances",
                "retry": True,
                "binary": True,
                "params": {"instanceName": "ghl-x"},
            }
        ]
        assert profile.phone == "5215512345678"
        assert profile.profile_name == "Ventas"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_evolution_fetch_profile_survives_unreadable_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un cuerpo que no es JSON deja el perfil vacio en vez de reventar.

    El perfil es cosmetico: si no se puede leer, la instancia sigue sirviendo y
    la pantalla cae al nombre interno."""
    http = StubHTTPClient(
        {},
        binary_response=BinaryResponse(content=b"<html>502</html>", headers=httpx.Headers({})),
    )
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="ghl-x",
    )

    try:
        profile = await client.fetch_profile()

        assert profile.phone is None
        assert profile.profile_name is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_evolution_send_whatsapp_audio_uses_its_own_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La nota de voz va por /message/sendWhatsAppAudio y no se reintenta.

    Por sendMedia con mediatype audio saldria como archivo adjunto en vez de nota
    de voz; y como es un envio, un reintento duplicaria el mensaje."""
    http = StubHTTPClient({"key": {"id": "evo-audio-1"}})
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_kwargs: http)
    client = EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
    )

    try:
        result = await client.send_whatsapp_audio(
            "5215550000001",
            "https://cdn.example.test/nota.ogg",
        )

        assert http.calls == [
            {
                "method": "POST",
                "path": "/message/sendWhatsAppAudio/recall-sales",
                "retry": False,
                "json": {
                    "number": "5215550000001",
                    "audio": "https://cdn.example.test/nota.ogg",
                },
            }
        ]
        assert result.message_id == "evo-audio-1"
        assert result.accepted is True
        assert isinstance(client, VoiceNoteSender)
    finally:
        await client.aclose()
