"""Esquemas normalizados: la forma comun a la que se aplanan Evolution y WABA.

El resto de la app trabaja SOLO con estos tipos y no sabe cual proveedor esta
por debajo. Ahi vive la parte "agnostica".
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACTS = "contacts"
    INTERACTIVE = "interactive"
    BUTTON = "button"
    REACTION = "reaction"
    UNKNOWN = "unknown"


class DeliveryStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    DELETED = "deleted"
    UNKNOWN = "unknown"


class SendResult(BaseModel):
    """Resultado de un envio. accepted=True solo dice que el proveedor lo acepto,
    NO que se entrego (para eso llega un StatusUpdate al webhook)."""

    provider: str
    message_id: str | None = None
    accepted: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class InboundMessage(BaseModel):
    """Mensaje entrante ya normalizado."""

    provider: str
    channel_number: str  # el numero/instancia del negocio que recibio (phone_number_id o instance)
    from_number: str  # remitente (wa_id)
    message_id: str
    type: MessageType = MessageType.UNKNOWN
    text: str | None = None
    media: dict[str, Any] | None = None  # id/link, mime_type, filename, caption
    interactive: dict[str, Any] | None = None  # respuesta de boton/lista
    timestamp: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class StatusUpdate(BaseModel):
    """Actualizacion de estado de entrega ya normalizada."""

    provider: str
    message_id: str
    status: DeliveryStatus = DeliveryStatus.UNKNOWN
    recipient: str | None = None
    timestamp: datetime | None = None
    error: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
