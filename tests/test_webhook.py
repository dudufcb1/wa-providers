from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

import pytest

from wa_providers import (
    DeliveryStatus,
    MessageType,
    parse_cloudapi,
    parse_evolution,
    parse_evolution_status,
    verify_cloudapi,
    verify_cloudapi_signature,
)
from wa_providers.schemas import InteractiveContent, MediaContent, MediaDownload


def _cloudapi_signature(raw_body: bytes, app_secret: str) -> str:
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _cloud_payload(
    messages: list[dict[str, Any]],
    contacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-number-id-1"},
                            "contacts": contacts or [],
                            "messages": messages,
                        }
                    }
                ]
            }
        ]
    }


def _evolution_payload(
    message: dict[str, Any],
    *,
    key: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_data: dict[str, Any] = {
        "key": {
            "remoteJid": "5215550000001@s.whatsapp.net",
            "fromMe": False,
            "id": "evolution-message-id",
            **(key or {}),
        },
        "message": message,
        "messageTimestamp": "1710000100",
        **(data or {}),
    }
    return {
        "event": "messages.upsert",
        "instance": "recall-sales",
        "data": event_data,
    }


def test_normalized_content_models_have_safe_defaults() -> None:
    assert MediaContent() == MediaContent(
        id=None,
        url=None,
        mime_type=None,
        filename=None,
        caption=None,
    )
    assert InteractiveContent() == InteractiveContent(type=None, id=None, title=None)

    download = MediaDownload(provider="cloudapi")

    assert download.content is None
    assert download.base64 is None
    assert download.mime_type is None
    assert download.filename is None
    assert download.raw == {}


def test_verify_cloudapi_signature_accepts_valid_signature() -> None:
    raw_body = b'{"object":"whatsapp_business_account"}'
    app_secret = "meta-app-secret"

    assert verify_cloudapi_signature(
        raw_body,
        _cloudapi_signature(raw_body, app_secret),
        app_secret,
    )


def test_verify_cloudapi_signature_rejects_signature_for_different_body() -> None:
    raw_body = b'{"messages":[]}'
    signature = _cloudapi_signature(raw_body, "meta-app-secret")

    assert not verify_cloudapi_signature(raw_body + b" ", signature, "meta-app-secret")


@pytest.mark.parametrize("signature_header", [None, ""])
def test_verify_cloudapi_signature_rejects_missing_header(
    signature_header: str | None,
) -> None:
    assert not verify_cloudapi_signature(b"{}", signature_header, "meta-app-secret")


@pytest.mark.parametrize(
    "signature_header",
    [
        "not-a-signature",
        "sha1=0123456789abcdef",
        "sha256=not-hexadecimal",
        "sha256=",
        "sha256=" + "ñ" * 64,
    ],
)
def test_verify_cloudapi_signature_rejects_malformed_header(
    signature_header: str,
) -> None:
    assert not verify_cloudapi_signature(b"{}", signature_header, "meta-app-secret")


def test_verify_cloudapi_signature_rejects_missing_app_secret() -> None:
    assert not verify_cloudapi_signature(b"{}", "sha256=anything", "")


def test_verify_cloudapi_returns_challenge_for_valid_handshake() -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "recall-token",
        "hub.challenge": "challenge-123",
    }

    assert verify_cloudapi(params, "recall-token") == "challenge-123"


def test_verify_cloudapi_accepts_unicode_token_without_type_error() -> None:
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "tökén-seguro",
        "hub.challenge": "challenge-123",
    }

    assert verify_cloudapi(params, "tökén-seguro") == "challenge-123"


@pytest.mark.parametrize(
    "params",
    [
        {
            "hub.mode": "unsubscribe",
            "hub.verify_token": "recall-token",
            "hub.challenge": "challenge-123",
        },
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "challenge-123",
        },
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "recall-token",
        },
        {
            "hub.mode": "subscribe",
            "hub.verify_token": "recall-token",
            "hub.challenge": 123,
        },
    ],
)
def test_verify_cloudapi_rejects_invalid_handshake(params: dict[str, Any]) -> None:
    assert verify_cloudapi(params, "recall-token") is None


def test_parse_cloudapi_flattens_multiple_messages_and_statuses() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "phone-number-id-1"},
                            "contacts": [
                                {
                                    "wa_id": "5215550000002",
                                    "profile": {"name": "Remitente dos"},
                                },
                                {
                                    "wa_id": "5215550000001",
                                    "profile": {"name": "Remitente uno"},
                                },
                            ],
                            "messages": [
                                {
                                    "from": "5215550000001",
                                    "id": "wamid.inbound-text",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Hola"},
                                },
                                {
                                    "from": "5215550000002",
                                    "id": "wamid.inbound-image",
                                    "timestamp": "1710000001",
                                    "type": "image",
                                    "image": {
                                        "id": "media-id-1",
                                        "mime_type": "image/jpeg",
                                        "caption": "Comprobante",
                                    },
                                },
                            ],
                            "statuses": [
                                {
                                    "id": "wamid.outbound-delivered",
                                    "recipient_id": "5215550000003",
                                    "status": "delivered",
                                    "timestamp": "1710000002",
                                },
                                {
                                    "id": "wamid.outbound-failed",
                                    "recipient_id": "5215550000004",
                                    "status": "failed",
                                    "timestamp": "1710000003",
                                    "errors": [
                                        {
                                            "code": 131047,
                                            "title": "Re-engagement message",
                                        }
                                    ],
                                },
                            ],
                        },
                    }
                ]
            }
        ],
    }

    messages, statuses = parse_cloudapi(payload)

    assert [message.message_id for message in messages] == [
        "wamid.inbound-text",
        "wamid.inbound-image",
    ]
    assert all(message.provider == "cloudapi" for message in messages)
    assert all(message.channel_number == "phone-number-id-1" for message in messages)
    assert messages[0].from_number == "5215550000001"
    assert messages[0].sender_name == "Remitente uno"
    assert messages[0].type is MessageType.TEXT
    assert messages[0].text == "Hola"
    assert messages[0].timestamp == datetime.fromtimestamp(1710000000, tz=timezone.utc)
    assert messages[1].type is MessageType.IMAGE
    assert messages[1].sender_name == "Remitente dos"
    assert messages[1].media == MediaContent(
        id="media-id-1",
        mime_type="image/jpeg",
        caption="Comprobante",
    )

    assert [status.message_id for status in statuses] == [
        "wamid.outbound-delivered",
        "wamid.outbound-failed",
    ]
    assert statuses[0].status is DeliveryStatus.DELIVERED
    assert statuses[0].recipient == "5215550000003"
    assert statuses[1].status is DeliveryStatus.FAILED
    assert statuses[1].error == {
        "code": 131047,
        "title": "Re-engagement message",
    }


@pytest.mark.parametrize(
    ("reply_type", "reply_id", "title"),
    [
        ("list_reply", "document:tax-status", "Constancia fiscal"),
        ("button_reply", "flow:continue", "Continuar"),
    ],
)
def test_parse_cloudapi_normalizes_interactive_reply_exact_id(
    reply_type: str,
    reply_id: str,
    title: str,
) -> None:
    message = {
        "from": "5215550000001",
        "id": "wamid.interactive",
        "type": "interactive",
        "interactive": {
            "type": reply_type,
            reply_type: {"id": reply_id, "title": title},
        },
    }

    messages, _ = parse_cloudapi(_cloud_payload([message]))

    assert messages[0].type is MessageType.INTERACTIVE
    assert messages[0].interactive == InteractiveContent(
        type=reply_type,
        id=reply_id,
        title=title,
    )
    assert messages[0].text == title


def test_parse_cloudapi_normalizes_legacy_button_payload_and_text() -> None:
    message = {
        "from": "5215550000001",
        "id": "wamid.button",
        "type": "button",
        "button": {"payload": "flow:approve", "text": "Aprobar"},
    }

    messages, _ = parse_cloudapi(_cloud_payload([message]))

    assert messages[0].type is MessageType.BUTTON
    assert messages[0].interactive == InteractiveContent(
        type="button",
        id="flow:approve",
        title="Aprobar",
    )
    assert messages[0].text == "Aprobar"


@pytest.mark.parametrize(
    ("message_type", "raw_media", "expected"),
    [
        (
            "image",
            {
                "id": "image-id",
                "mime_type": "image/jpeg",
                "caption": "Foto",
            },
            MediaContent(id="image-id", mime_type="image/jpeg", caption="Foto"),
        ),
        (
            "document",
            {
                "id": "document-id",
                "mime_type": "application/pdf",
                "filename": "document.pdf",
                "caption": "Documento",
            },
            MediaContent(
                id="document-id",
                mime_type="application/pdf",
                filename="document.pdf",
                caption="Documento",
            ),
        ),
        (
            "audio",
            {"id": "audio-id", "mime_type": "audio/ogg"},
            MediaContent(id="audio-id", mime_type="audio/ogg"),
        ),
        (
            "video",
            {
                "id": "video-id",
                "mime_type": "video/mp4",
                "caption": "Video",
            },
            MediaContent(id="video-id", mime_type="video/mp4", caption="Video"),
        ),
        (
            "sticker",
            {"id": "sticker-id", "mime_type": "image/webp"},
            MediaContent(id="sticker-id", mime_type="image/webp"),
        ),
    ],
)
def test_parse_cloudapi_normalizes_typed_media(
    message_type: str,
    raw_media: dict[str, Any],
    expected: MediaContent,
) -> None:
    message = {
        "from": "5215550000001",
        "id": f"wamid.{message_type}",
        "type": message_type,
        message_type: raw_media,
    }

    messages, _ = parse_cloudapi(_cloud_payload([message]))

    assert messages[0].type is MessageType(message_type)
    assert messages[0].media == expected


def test_parse_evolution_normalizes_basic_text_message() -> None:
    payload = {
        "event": "messages.upsert",
        "instance": "recall-sales",
        "data": {
            "key": {
                "remoteJid": "5215550000001@s.whatsapp.net",
                "fromMe": False,
                "id": "evolution-message-id",
            },
            "message": {"conversation": "Mensaje desde Evolution"},
            "messageTimestamp": "1710000100",
            "pushName": "Eduardo",
        },
    }

    messages = parse_evolution(payload)

    assert len(messages) == 1
    message = messages[0]
    assert message.provider == "evolution"
    assert message.channel_number == "recall-sales"
    assert message.from_number == "5215550000001"
    assert message.message_id == "evolution-message-id"
    assert message.sender_name == "Eduardo"
    assert message.from_me is False
    assert message.remote_jid == "5215550000001@s.whatsapp.net"
    assert message.type is MessageType.TEXT
    assert message.text == "Mensaje desde Evolution"
    assert message.timestamp == datetime.fromtimestamp(1710000100, tz=timezone.utc)


def test_parse_evolution_normalizes_extended_text_and_from_me() -> None:
    payload = _evolution_payload(
        {"extendedTextMessage": {"text": "Respuesta enlazada"}},
        key={"fromMe": True},
    )

    message = parse_evolution(payload)[0]

    assert message.type is MessageType.TEXT
    assert message.text == "Respuesta enlazada"
    assert message.from_me is True


@pytest.mark.parametrize(
    ("key_identity", "data_identity", "expected_number"),
    [
        ({"remoteJidAlt": "5215550000002@s.whatsapp.net"}, {}, "5215550000002"),
        ({"senderPn": "5215550000003@s.whatsapp.net"}, {}, "5215550000003"),
        ({}, {"senderPn": "+5215550000004"}, "5215550000004"),
    ],
)
def test_parse_evolution_resolves_lid_from_supported_phone_identity(
    key_identity: dict[str, Any],
    data_identity: dict[str, Any],
    expected_number: str,
) -> None:
    payload = _evolution_payload(
        {"conversation": "Mensaje LID"},
        key={"remoteJid": "opaque-device-id@lid", **key_identity},
        data=data_identity,
    )

    message = parse_evolution(payload)[0]

    assert message.from_number == expected_number
    assert message.remote_jid == "opaque-device-id@lid"


def test_parse_evolution_rejects_unresolvable_lid() -> None:
    payload = _evolution_payload(
        {"conversation": "Mensaje sin identidad telefonica"},
        key={
            "remoteJid": "opaque-device-id@lid",
            "remoteJidAlt": "another-opaque-id@lid",
        },
    )

    assert parse_evolution(payload) == []


@pytest.mark.parametrize(
    "invalid_identity",
    [
        "opaque-device-id@lid",
        "opaque-device-id",
        "5215550000005@c.us",
        "5215550000005@unknown.example",
        "+52155invalid",
        "１２３４５",
        "１２３４５@s.whatsapp.net",
    ],
)
def test_parse_evolution_rejects_opaque_lid_sender_pn(invalid_identity: str) -> None:
    payload = _evolution_payload(
        {"conversation": "Mensaje con identidad opaca"},
        key={
            "remoteJid": "opaque-device-id@lid",
            "senderPn": invalid_identity,
        },
    )

    assert parse_evolution(payload) == []


def test_parse_evolution_rejects_non_numeric_remote_jid_alt() -> None:
    payload = _evolution_payload(
        {"conversation": "Mensaje con identidad opaca"},
        key={
            "remoteJid": "opaque-device-id@lid",
            "remoteJidAlt": "opaque-device-id@s.whatsapp.net",
        },
    )

    assert parse_evolution(payload) == []


@pytest.mark.parametrize(
    ("field", "root_type", "expected_type", "raw_media", "expected_media"),
    [
        (
            "imageMessage",
            "imageMessage",
            MessageType.IMAGE,
            {
                "url": "https://media.example.test/image",
                "mimetype": "image/jpeg",
                "caption": "Comprobante",
            },
            MediaContent(
                url="https://media.example.test/image",
                mime_type="image/jpeg",
                caption="Comprobante",
            ),
        ),
        (
            "documentMessage",
            "documentMessage",
            MessageType.DOCUMENT,
            {
                "url": "https://media.example.test/document",
                "mimetype": "application/pdf",
                "fileName": "constancia.pdf",
                "caption": "Constancia",
            },
            MediaContent(
                url="https://media.example.test/document",
                mime_type="application/pdf",
                filename="constancia.pdf",
                caption="Constancia",
            ),
        ),
        (
            "audioMessage",
            "audioMessage",
            MessageType.AUDIO,
            {
                "url": "https://media.example.test/audio",
                "mimetype": "audio/ogg",
            },
            MediaContent(
                url="https://media.example.test/audio",
                mime_type="audio/ogg",
            ),
        ),
        (
            "videoMessage",
            "videoMessage",
            MessageType.VIDEO,
            {
                "url": "https://media.example.test/video",
                "mimetype": "video/mp4",
                "caption": "Recorrido",
            },
            MediaContent(
                url="https://media.example.test/video",
                mime_type="video/mp4",
                caption="Recorrido",
            ),
        ),
    ],
)
def test_parse_evolution_normalizes_four_media_types(
    field: str,
    root_type: str,
    expected_type: MessageType,
    raw_media: dict[str, Any],
    expected_media: MediaContent,
) -> None:
    payload = _evolution_payload(
        {field: raw_media},
        data={"messageType": root_type},
    )

    message = parse_evolution(payload)[0]

    assert message.type is expected_type
    assert message.text is None
    assert message.media == expected_media


def test_parse_evolution_uses_root_message_type_as_fallback() -> None:
    payload = _evolution_payload({}, data={"messageType": "documentMessage"})

    message = parse_evolution(payload)[0]

    assert message.type is MessageType.DOCUMENT
    assert message.media is None


def test_parse_evolution_ignores_payload_without_message_key() -> None:
    assert parse_evolution({"instance": "recall-sales", "data": {}}) == []


def test_parse_evolution_ignores_payload_without_remote_jid() -> None:
    payload = _evolution_payload(
        {"conversation": "Sin remitente"},
        key={"remoteJid": ""},
    )

    assert parse_evolution(payload) == []


def test_evolution_parsers_do_not_cross_message_and_status_events() -> None:
    upsert_payload = _evolution_payload({"conversation": "Mensaje entrante"})
    update_payload = {
        "event": "messages.update",
        "instance": "recall-sales",
        "data": {
            "key": {
                "id": "evolution-message-id",
                "remoteJid": "5215550000001@s.whatsapp.net",
            },
            "message": {"conversation": "No debe entrar al flujo"},
            "status": "READ",
        },
    }

    assert parse_evolution_status(upsert_payload) == []
    assert parse_evolution(update_payload) == []


def test_evolution_parsers_accept_config_style_event_names() -> None:
    upsert_payload = _evolution_payload({"conversation": "Mensaje entrante"})
    upsert_payload["event"] = "MESSAGES_UPSERT"
    update_payload = {
        "event": "MESSAGES_UPDATE",
        "data": {"keyId": "message-1", "status": "READ"},
    }

    assert len(parse_evolution(upsert_payload)) == 1
    assert len(parse_evolution_status(update_payload)) == 1


@pytest.mark.parametrize(
    ("raw_status", "expected_status"),
    [
        ("SERVER_ACK", DeliveryStatus.SENT),
        ("DELIVERY_ACK", DeliveryStatus.DELIVERED),
        ("READ", DeliveryStatus.READ),
        ("PLAYED", DeliveryStatus.READ),
        ("ERROR", DeliveryStatus.FAILED),
        ("DELETED", DeliveryStatus.DELETED),
        ("PENDING", DeliveryStatus.UNKNOWN),
        ("future_status", DeliveryStatus.UNKNOWN),
    ],
)
def test_parse_evolution_status_normalizes_delivery_updates(
    raw_status: str,
    expected_status: DeliveryStatus,
) -> None:
    payload = {
        "event": "messages.update",
        "instance": "recall-sales",
        "data": {
            "keyId": "evolution-message-id",
            "remoteJid": "5215550000001@s.whatsapp.net",
            "fromMe": True,
            "status": raw_status,
            "messageTimestamp": "1710000100",
        },
    }

    statuses = parse_evolution_status(payload)

    assert len(statuses) == 1
    assert statuses[0].provider == "evolution"
    assert statuses[0].message_id == "evolution-message-id"
    assert statuses[0].status is expected_status
    assert statuses[0].recipient == "5215550000001"
    assert statuses[0].timestamp == datetime.fromtimestamp(1710000100, tz=timezone.utc)


def test_parse_evolution_status_supports_nested_keys_and_multiple_updates() -> None:
    payload = {
        "event": "messages.update",
        "data": [
            {
                "key": {
                    "id": "message-1",
                    "remoteJid": "5215550000001@s.whatsapp.net",
                },
                "status": "DELIVERY_ACK",
            },
            {"keyId": "message-2", "status": "READ"},
            {"status": "READ"},
        ],
    }

    statuses = parse_evolution_status(payload)

    assert [status.message_id for status in statuses] == ["message-1", "message-2"]
    assert [status.status for status in statuses] == [
        DeliveryStatus.DELIVERED,
        DeliveryStatus.READ,
    ]


def test_parse_evolution_status_does_not_treat_lid_as_phone_number() -> None:
    payload = {
        "event": "messages.update",
        "data": {
            "keyId": "message-1",
            "remoteJid": "opaque-device-id@lid",
            "status": "READ",
        },
    }

    statuses = parse_evolution_status(payload)

    assert statuses[0].recipient is None


def test_parse_evolution_ignores_broadcast_and_newsletter_jids() -> None:
    for jid in ("status@broadcast", "120363000000000000@newsletter"):
        payload = _evolution_payload(
            {"conversation": "Difusion"},
            key={"remoteJid": jid},
        )

        assert parse_evolution(payload) == []


def test_parse_evolution_uses_group_participant_as_sender() -> None:
    payload = _evolution_payload(
        {"conversation": "Mensaje en grupo"},
        key={
            "remoteJid": "120363000000000000@g.us",
            "participant": "5215550000009@s.whatsapp.net",
        },
    )

    message = parse_evolution(payload)[0]

    assert message.is_group is True
    assert message.from_number == "5215550000009"
    assert message.remote_jid == "120363000000000000@g.us"


def test_parse_evolution_resolves_opaque_group_participant() -> None:
    payload = _evolution_payload(
        {"conversation": "Mensaje en grupo desde otro dispositivo"},
        key={
            "remoteJid": "120363000000000000@g.us",
            "participant": "opaque-device-id@lid",
            "participantAlt": "5215550000009@s.whatsapp.net",
        },
    )

    message = parse_evolution(payload)[0]

    assert message.is_group is True
    assert message.from_number == "5215550000009"


def test_parse_evolution_discards_group_without_resolvable_participant() -> None:
    payload = _evolution_payload(
        {"conversation": "Mensaje en grupo sin autor"},
        key={
            "remoteJid": "120363000000000000@g.us",
            "participant": "opaque-device-id@lid",
        },
    )

    assert parse_evolution(payload) == []


def test_parse_evolution_marks_direct_messages_as_not_group() -> None:
    payload = _evolution_payload({"conversation": "Mensaje directo"})

    assert parse_evolution(payload)[0].is_group is False


def test_parse_evolution_discards_message_without_id() -> None:
    for empty_id in ("", None):
        payload = _evolution_payload(
            {"conversation": "Sin identificador"},
            key={"id": empty_id},
        )

        assert parse_evolution(payload) == []


@pytest.mark.parametrize(
    ("message", "expected_type", "expected_text"),
    [
        ({"reactionMessage": {"text": "\N{THUMBS UP SIGN}"}}, MessageType.REACTION, "\N{THUMBS UP SIGN}"),
        (
            {"locationMessage": {"degreesLatitude": 19.4, "name": "Oficina"}},
            MessageType.LOCATION,
            "Oficina",
        ),
        (
            {"locationMessage": {"degreesLatitude": 19.4, "address": "Reforma 222"}},
            MessageType.LOCATION,
            "Reforma 222",
        ),
        (
            {"contactMessage": {"displayName": "Renata", "vcard": "BEGIN:VCARD"}},
            MessageType.CONTACTS,
            "Renata",
        ),
    ],
)
def test_parse_evolution_maps_non_media_message_types(
    message: dict[str, Any],
    expected_type: MessageType,
    expected_text: str,
) -> None:
    inbound = parse_evolution(_evolution_payload(message))[0]

    assert inbound.type is expected_type
    assert inbound.text == expected_text
    assert inbound.media is None


def test_parse_evolution_maps_sticker_as_media() -> None:
    payload = _evolution_payload(
        {"stickerMessage": {"mimetype": "image/webp", "url": "https://cdn.test/s.enc"}},
    )

    inbound = parse_evolution(payload)[0]

    assert inbound.type is MessageType.STICKER
    assert inbound.media == MediaContent(
        mime_type="image/webp",
        url="https://cdn.test/s.enc",
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            {
                "buttonsResponseMessage": {
                    "selectedButtonId": "continuar",
                    "selectedDisplayText": "Continuar",
                }
            },
            InteractiveContent(type="button_reply", id="continuar", title="Continuar"),
        ),
        (
            {
                "templateButtonReplyMessage": {
                    "selectedId": "continuar",
                    "selectedDisplayText": "Continuar",
                }
            },
            InteractiveContent(type="button_reply", id="continuar", title="Continuar"),
        ),
        (
            {
                "listResponseMessage": {
                    "title": "Agendar",
                    "singleSelectReply": {"selectedRowId": "slot-1"},
                }
            },
            InteractiveContent(type="list_reply", id="slot-1", title="Agendar"),
        ),
    ],
)
def test_parse_evolution_normalizes_interactive_replies(
    message: dict[str, Any],
    expected: InteractiveContent,
) -> None:
    inbound = parse_evolution(_evolution_payload(message))[0]

    assert inbound.type is MessageType.INTERACTIVE
    assert inbound.interactive == expected
    assert inbound.text == expected.title
