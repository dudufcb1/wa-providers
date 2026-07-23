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


class TemplateStatus(str, Enum):
    """Estado de revision de una plantilla en Meta.

    Solo `APPROVED` se puede enviar; el resto existe para explicarle al usuario
    por que una plantilla que ve en su cuenta no aparece disponible.
    """

    APPROVED = "approved"
    PENDING = "pending"
    IN_APPEAL = "in_appeal"
    REJECTED = "rejected"
    PAUSED = "paused"
    DISABLED = "disabled"
    LIMIT_EXCEEDED = "limit_exceeded"
    PENDING_DELETION = "pending_deletion"
    DELETED = "deleted"
    UNKNOWN = "unknown"


class TemplateCategory(str, Enum):
    """Categoria comercial de la plantilla, que es lo que Meta cobra distinto."""

    AUTHENTICATION = "authentication"
    MARKETING = "marketing"
    UTILITY = "utility"
    UNKNOWN = "unknown"


class Template(BaseModel):
    """Plantilla del catalogo del proveedor, ya normalizada.

    `variables` trae los marcadores del cuerpo en orden de aparicion, sin
    repetir: `["1", "2"]` con el formato posicional y `["nombre", "folio"]` con
    el formato nombrado. Es lo que necesita una pantalla para pedir los valores
    antes de enviar.
    """

    provider: str
    id: str | None = None
    name: str
    language: str
    status: TemplateStatus = TemplateStatus.UNKNOWN
    category: TemplateCategory = TemplateCategory.UNKNOWN
    body: str | None = None
    variables: list[str] = Field(default_factory=list)
    components: list[dict[str, Any]] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_sendable(self) -> bool:
        """Solo una plantilla aprobada se puede mandar; las demas las rechaza Meta."""
        return self.status is TemplateStatus.APPROVED


class SendResult(BaseModel):
    """Resultado de un envio. accepted=True solo dice que el proveedor lo acepto,
    NO que se entrego (para eso llega un StatusUpdate al webhook)."""

    provider: str
    message_id: str | None = None
    accepted: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class MediaContent(BaseModel):
    """Contenido multimedia normalizado de un mensaje entrante."""

    id: str | None = None
    url: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    caption: str | None = None


class InteractiveContent(BaseModel):
    """Seleccion interactiva normalizada de un boton o una lista."""

    type: str | None = None
    id: str | None = None
    title: str | None = None


class InstanceProfile(BaseModel):
    """Datos del numero ya vinculado a una instancia: su telefono y su perfil.

    `phone` son los digitos del JID tal como los entrega el motor: sin `+` y, en
    Mexico, con el `1` movil historico que mete Baileys (`5215512345678`).
    Normalizarlo es del consumidor, que es quien sabe contra que formato machea
    su sistema. Los JID `@lid` no traen numero, asi que ahi queda en None.
    """

    phone: str | None = None
    profile_name: str | None = None


class MediaDownload(BaseModel):
    """Resultado normalizado de una descarga multimedia."""

    provider: str
    content: bytes | None = None
    base64: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class InboundMessage(BaseModel):
    """Mensaje entrante ya normalizado."""

    provider: str
    channel_number: str  # el numero/instancia del negocio que recibio (phone_number_id o instance)
    from_number: str  # remitente (wa_id)
    message_id: str
    sender_name: str | None = None
    from_me: bool = False
    is_group: bool = False  # en grupos, from_number es el participante que escribio
    remote_jid: str | None = None
    type: MessageType = MessageType.UNKNOWN
    text: str | None = None
    media: MediaContent | None = None
    interactive: InteractiveContent | None = None
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
