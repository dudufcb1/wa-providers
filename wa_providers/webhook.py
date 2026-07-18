"""Helpers de webhook, framework-agnosticos.

Reciben el payload crudo (dict) y devuelven los tipos normalizados. La RUTA del
webhook (FastAPI @router, controller de Odoo, etc.) la pone cada proyecto y solo
llama a estas funciones. Aqui NO hay framework.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

from .schemas import DeliveryStatus, InboundMessage, MessageType, StatusUpdate


def _epoch(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _mtype(raw: str | None) -> MessageType:
    try:
        return MessageType(raw or "")
    except ValueError:
        return MessageType.UNKNOWN


def _dstatus(raw: str | None) -> DeliveryStatus:
    try:
        return DeliveryStatus((raw or "").lower())
    except ValueError:
        return DeliveryStatus.UNKNOWN


# ---------------------------------------------------------------- Cloud API (WABA)


def verify_cloudapi(params: dict[str, Any], verify_token: str) -> str | None:
    """Handshake GET de Meta. Devuelve el hub.challenge si el token coincide.

    En tu ruta: si devuelve un str, respondelo como texto plano (200); si None, 403.
    """
    provided_token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if (
        params.get("hub.mode") == "subscribe"
        and isinstance(provided_token, str)
        and isinstance(challenge, str)
        and bool(verify_token)
        and hmac.compare_digest(provided_token.encode("utf-8"), verify_token.encode("utf-8"))
    ):
        return challenge
    return None


def verify_cloudapi_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    """Valida la firma HMAC-SHA256 de un webhook POST de Meta."""
    if not signature_header or not app_secret:
        return False
    prefix, separator, encoded_signature = signature_header.strip().partition("=")
    if prefix != "sha256" or separator != "=" or len(encoded_signature) != 64:
        return False
    try:
        provided_signature = bytes.fromhex(encoded_signature)
    except ValueError:
        return False
    expected_signature = hmac.digest(app_secret.encode("utf-8"), raw_body, hashlib.sha256)
    return hmac.compare_digest(expected_signature, provided_signature)


def parse_cloudapi(payload: dict[str, Any]) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    """Aplana el POST del webhook de WABA a (mensajes, estados)."""
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            channel = (value.get("metadata") or {}).get("phone_number_id", "")
            for m in value.get("messages", []) or []:
                messages.append(_cloud_message(m, channel))
            for s in value.get("statuses", []) or []:
                statuses.append(_cloud_status(s))
    return messages, statuses


def _cloud_message(m: dict[str, Any], channel: str) -> InboundMessage:
    mtype = m.get("type", "unknown")
    text: str | None = None
    media: dict[str, Any] | None = None
    interactive: dict[str, Any] | None = None
    if mtype == "text":
        text = (m.get("text") or {}).get("body")
    elif mtype in ("image", "document", "audio", "video", "sticker"):
        media = m.get(mtype)
    elif mtype == "interactive":
        interactive = m.get("interactive")
    elif mtype == "button":
        text = (m.get("button") or {}).get("text")
    return InboundMessage(
        provider="cloudapi",
        channel_number=channel,
        from_number=m.get("from", ""),
        message_id=m.get("id", ""),
        type=_mtype(mtype),
        text=text,
        media=media,
        interactive=interactive,
        timestamp=_epoch(m.get("timestamp")),
        raw=m,
    )


def _cloud_status(s: dict[str, Any]) -> StatusUpdate:
    errors = s.get("errors") or []
    return StatusUpdate(
        provider="cloudapi",
        message_id=s.get("id", ""),
        status=_dstatus(s.get("status")),
        recipient=s.get("recipient_id"),
        timestamp=_epoch(s.get("timestamp")),
        error=errors[0] if errors else None,
        raw=s,
    )


# ---------------------------------------------------------------- Evolution


def parse_evolution(payload: dict[str, Any]) -> list[InboundMessage]:
    """Aplana un evento MESSAGES_UPSERT de Evolution a InboundMessage."""
    data = payload.get("data") or {}
    key = data.get("key") or {}
    if not key:
        return []
    remote = key.get("remoteJid", "") or ""
    from_number = remote.split("@")[0] if remote else ""
    message = data.get("message") or {}
    text = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text")
    return [
        InboundMessage(
            provider="evolution",
            channel_number=payload.get("instance", ""),
            from_number=from_number,
            message_id=key.get("id", ""),
            type=MessageType.TEXT if text else MessageType.UNKNOWN,
            text=text,
            media=None,
            interactive=None,
            timestamp=_epoch(data.get("messageTimestamp")),
            raw=payload,
        )
    ]
