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
    verify_cloudapi,
    verify_cloudapi_signature,
)


def _cloudapi_signature(raw_body: bytes, app_secret: str) -> str:
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


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
    assert messages[0].type is MessageType.TEXT
    assert messages[0].text == "Hola"
    assert messages[0].timestamp == datetime.fromtimestamp(1710000000, tz=timezone.utc)
    assert messages[1].type is MessageType.IMAGE
    assert messages[1].media == {
        "id": "media-id-1",
        "mime_type": "image/jpeg",
        "caption": "Comprobante",
    }

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
        },
    }

    messages = parse_evolution(payload)

    assert len(messages) == 1
    message = messages[0]
    assert message.provider == "evolution"
    assert message.channel_number == "recall-sales"
    assert message.from_number == "5215550000001"
    assert message.message_id == "evolution-message-id"
    assert message.type is MessageType.TEXT
    assert message.text == "Mensaje desde Evolution"
    assert message.timestamp == datetime.fromtimestamp(1710000100, tz=timezone.utc)


def test_parse_evolution_ignores_payload_without_message_key() -> None:
    assert parse_evolution({"instance": "recall-sales", "data": {}}) == []
