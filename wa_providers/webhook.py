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

from .schemas import (
    DeliveryStatus,
    InboundMessage,
    InteractiveContent,
    MediaContent,
    MessageType,
    StatusUpdate,
)


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


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _matches_evolution_event(payload: dict[str, Any], expected: str) -> bool:
    raw_event = _string(payload.get("event"))
    if raw_event is None:
        return False
    normalized_event = raw_event.strip().lower().replace("_", ".").replace("-", ".")
    return normalized_event == expected


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
            contact_names = _cloud_contact_names(value.get("contacts"))
            for m in value.get("messages", []) or []:
                messages.append(
                    _cloud_message(
                        m,
                        channel,
                        contact_names.get(m.get("from", "")),
                    )
                )
            for s in value.get("statuses", []) or []:
                statuses.append(_cloud_status(s))
    return messages, statuses


def _cloud_contact_names(raw_contacts: Any) -> dict[str, str]:
    contact_names: dict[str, str] = {}
    if not isinstance(raw_contacts, list):
        return contact_names
    for raw_contact in raw_contacts:
        contact = _mapping(raw_contact)
        wa_id = _string(contact.get("wa_id"))
        name = _string(_mapping(contact.get("profile")).get("name"))
        if wa_id and name:
            contact_names[wa_id] = name
    return contact_names


def _cloud_media(raw_media: Any) -> MediaContent:
    media = _mapping(raw_media)
    return MediaContent(
        id=_string(media.get("id")),
        url=_string(media.get("url") or media.get("link")),
        mime_type=_string(media.get("mime_type")),
        filename=_string(media.get("filename")),
        caption=_string(media.get("caption")),
    )


def _cloud_interactive(raw_interactive: Any) -> tuple[InteractiveContent, str | None]:
    interactive = _mapping(raw_interactive)
    interactive_type = _string(interactive.get("type"))
    list_reply = _mapping(interactive.get("list_reply"))
    button_reply = _mapping(interactive.get("button_reply"))
    reply = list_reply or button_reply
    if interactive_type is None:
        if list_reply:
            interactive_type = "list_reply"
        elif button_reply:
            interactive_type = "button_reply"
    title = _string(reply.get("title"))
    return (
        InteractiveContent(
            type=interactive_type,
            id=_string(reply.get("id")),
            title=title,
        ),
        title,
    )


def _cloud_button(raw_button: Any) -> tuple[InteractiveContent, str | None]:
    button = _mapping(raw_button)
    title = _string(button.get("text"))
    return (
        InteractiveContent(
            type="button",
            id=_string(button.get("payload")),
            title=title,
        ),
        title,
    )


def _cloud_message(
    m: dict[str, Any],
    channel: str,
    sender_name: str | None,
) -> InboundMessage:
    mtype = m.get("type", "unknown")
    text: str | None = None
    media: MediaContent | None = None
    interactive: InteractiveContent | None = None
    if mtype == "text":
        text = (m.get("text") or {}).get("body")
    elif mtype in ("image", "document", "audio", "video", "sticker"):
        media = _cloud_media(m.get(mtype))
    elif mtype == "interactive":
        interactive, text = _cloud_interactive(m.get("interactive"))
    elif mtype == "button":
        interactive, text = _cloud_button(m.get("button"))
    return InboundMessage(
        provider="cloudapi",
        channel_number=channel,
        from_number=m.get("from", ""),
        message_id=m.get("id", ""),
        sender_name=sender_name,
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


_EVOLUTION_MESSAGE_TYPES = {
    "conversation": MessageType.TEXT,
    "extendedTextMessage": MessageType.TEXT,
    "imageMessage": MessageType.IMAGE,
    "documentMessage": MessageType.DOCUMENT,
    "audioMessage": MessageType.AUDIO,
    "videoMessage": MessageType.VIDEO,
}

_EVOLUTION_DELIVERY_STATUSES = {
    "ERROR": DeliveryStatus.FAILED,
    "PENDING": DeliveryStatus.UNKNOWN,
    "SERVER_ACK": DeliveryStatus.SENT,
    "DELIVERY_ACK": DeliveryStatus.DELIVERED,
    "READ": DeliveryStatus.READ,
    "PLAYED": DeliveryStatus.READ,
    "DELETED": DeliveryStatus.DELETED,
}


def _clean_jid(value: str) -> str:
    return value.split("@", 1)[0]


def _phone_identity(value: str, *, require_whatsapp_suffix: bool = False) -> str | None:
    if "@" in value:
        local_part, suffix = value.rsplit("@", 1)
        if suffix != "s.whatsapp.net":
            return None
    elif require_whatsapp_suffix:
        return None
    else:
        local_part = value
    normalized = local_part.removeprefix("+")
    return normalized if normalized.isascii() and normalized.isdigit() else None


def _evolution_sender(
    key: dict[str, Any],
    data: dict[str, Any],
) -> tuple[str, str] | None:
    remote_jid = _string(key.get("remoteJid"))
    if not remote_jid:
        return None
    resolved_jid = remote_jid
    if remote_jid.endswith("@lid"):
        remote_jid_alt = _string(key.get("remoteJidAlt"))
        sender_pn = _string(key.get("senderPn")) or _string(data.get("senderPn"))
        resolved_phone = (
            _phone_identity(remote_jid_alt, require_whatsapp_suffix=True)
            if remote_jid_alt
            else None
        )
        if resolved_phone is None and sender_pn:
            resolved_phone = _phone_identity(sender_pn)
        if resolved_phone is None:
            return None
        return resolved_phone, remote_jid
    return _clean_jid(resolved_jid), remote_jid


def _evolution_media(raw_media: Any) -> MediaContent:
    media = _mapping(raw_media)
    return MediaContent(
        id=_string(media.get("id")),
        url=_string(media.get("url")),
        mime_type=_string(media.get("mimetype")),
        filename=_string(media.get("fileName")),
        caption=_string(media.get("caption")),
    )


def _evolution_content(
    data: dict[str, Any],
) -> tuple[MessageType, str | None, MediaContent | None]:
    message = _mapping(data.get("message"))
    if "conversation" in message:
        return MessageType.TEXT, _string(message.get("conversation")), None
    if "extendedTextMessage" in message:
        extended = _mapping(message.get("extendedTextMessage"))
        return MessageType.TEXT, _string(extended.get("text")), None

    media_types = (
        ("imageMessage", MessageType.IMAGE),
        ("documentMessage", MessageType.DOCUMENT),
        ("audioMessage", MessageType.AUDIO),
        ("videoMessage", MessageType.VIDEO),
    )
    for field, message_type in media_types:
        if field in message:
            media = _evolution_media(message.get(field))
            return message_type, None, media

    raw_type = _string(data.get("messageType"))
    if raw_type in _EVOLUTION_MESSAGE_TYPES:
        return _EVOLUTION_MESSAGE_TYPES[raw_type], None, None
    return _mtype(raw_type), None, None


def parse_evolution(payload: dict[str, Any]) -> list[InboundMessage]:
    """Aplana un evento MESSAGES_UPSERT de Evolution a InboundMessage."""
    if not _matches_evolution_event(payload, "messages.upsert"):
        return []
    data = _mapping(payload.get("data"))
    key = _mapping(data.get("key"))
    if not key:
        return []
    sender = _evolution_sender(key, data)
    if sender is None:
        return []
    from_number, remote_jid = sender
    message_type, text, media = _evolution_content(data)
    return [
        InboundMessage(
            provider="evolution",
            channel_number=payload.get("instance", ""),
            from_number=from_number,
            message_id=key.get("id", ""),
            sender_name=_string(data.get("pushName")),
            from_me=bool(key.get("fromMe", False)),
            remote_jid=remote_jid,
            type=message_type,
            text=text,
            media=media,
            interactive=None,
            timestamp=_epoch(data.get("messageTimestamp")),
            raw=payload,
        )
    ]


def parse_evolution_status(payload: dict[str, Any]) -> list[StatusUpdate]:
    """Normaliza eventos MESSAGES_UPDATE de Evolution sin mezclarlos con mensajes."""
    if not _matches_evolution_event(payload, "messages.update"):
        return []
    raw_data = payload.get("data")
    updates = raw_data if isinstance(raw_data, list) else [raw_data]
    statuses: list[StatusUpdate] = []
    for raw_update in updates:
        update = _mapping(raw_update)
        key = _mapping(update.get("key"))
        message_id = _string(update.get("keyId")) or _string(key.get("id"))
        if not message_id:
            continue
        raw_status = (_string(update.get("status")) or "").upper()
        remote_jid = _string(update.get("remoteJid")) or _string(key.get("remoteJid"))
        raw_error = update.get("error")
        statuses.append(
            StatusUpdate(
                provider="evolution",
                message_id=message_id,
                status=_EVOLUTION_DELIVERY_STATUSES.get(
                    raw_status,
                    DeliveryStatus.UNKNOWN,
                ),
                recipient=_phone_identity(remote_jid) if remote_jid else None,
                timestamp=_epoch(update.get("messageTimestamp")),
                error=raw_error if isinstance(raw_error, dict) else None,
                raw=update,
            )
        )
    return statuses
