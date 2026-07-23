"""wa_providers: WhatsApp agnostico (Evolution + WABA) detras de una interfaz comun."""

from __future__ import annotations

from .base import BaseProvider
from .capabilities import (
    CloudMediaDownloader,
    EvolutionMediaDownloader,
    GenericMediaSender,
    HealthChecker,
    InstanceManager,
    InteractiveSender,
    ReadMarker,
    TemplateCatalog,
    TemplateSender,
    TextSender,
    VoiceNoteSender,
    WebhookConfigurator,
)
from .cloudapi import CloudAPIClient
from .evolution import EvolutionClient
from .exceptions import ProviderAPIError, ProviderTransportError, WAProviderError
from .factory import get_provider
from .schemas import (
    DeliveryStatus,
    InboundMessage,
    InstanceProfile,
    InteractiveContent,
    MediaContent,
    MediaDownload,
    MessageType,
    SendResult,
    StatusUpdate,
    Template,
    TemplateCategory,
    TemplateStatus,
)
from .webhook import (
    parse_cloudapi,
    parse_evolution,
    parse_evolution_status,
    verify_cloudapi,
    verify_cloudapi_signature,
)

__version__ = "0.4.0"

__all__ = [
    "BaseProvider",
    "CloudMediaDownloader",
    "CloudAPIClient",
    "EvolutionMediaDownloader",
    "EvolutionClient",
    "GenericMediaSender",
    "HealthChecker",
    "InstanceManager",
    "InstanceProfile",
    "InteractiveContent",
    "InteractiveSender",
    "MediaContent",
    "MediaDownload",
    "ReadMarker",
    "Template",
    "TemplateCatalog",
    "TemplateCategory",
    "TemplateSender",
    "TemplateStatus",
    "TextSender",
    "VoiceNoteSender",
    "WebhookConfigurator",
    "get_provider",
    "SendResult",
    "InboundMessage",
    "StatusUpdate",
    "MessageType",
    "DeliveryStatus",
    "parse_cloudapi",
    "parse_evolution",
    "parse_evolution_status",
    "verify_cloudapi",
    "verify_cloudapi_signature",
    "WAProviderError",
    "ProviderAPIError",
    "ProviderTransportError",
]
