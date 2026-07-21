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
    TemplateSender,
    TextSender,
    WebhookConfigurator,
)
from .cloudapi import CloudAPIClient
from .evolution import EvolutionClient
from .exceptions import ProviderAPIError, ProviderTransportError, WAProviderError
from .factory import get_provider
from .schemas import (
    DeliveryStatus,
    InboundMessage,
    InteractiveContent,
    MediaContent,
    MediaDownload,
    MessageType,
    SendResult,
    StatusUpdate,
)
from .webhook import (
    parse_cloudapi,
    parse_evolution,
    parse_evolution_status,
    verify_cloudapi,
    verify_cloudapi_signature,
)

__version__ = "0.3.0"

__all__ = [
    "BaseProvider",
    "CloudMediaDownloader",
    "CloudAPIClient",
    "EvolutionMediaDownloader",
    "EvolutionClient",
    "GenericMediaSender",
    "HealthChecker",
    "InstanceManager",
    "InteractiveContent",
    "InteractiveSender",
    "MediaContent",
    "MediaDownload",
    "ReadMarker",
    "TemplateSender",
    "TextSender",
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
