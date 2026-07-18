"""wa_providers: WhatsApp agnostico (Evolution + WABA) detras de una interfaz comun."""

from __future__ import annotations

from .base import BaseProvider
from .cloudapi import CloudAPIClient
from .evolution import EvolutionClient
from .exceptions import ProviderAPIError, ProviderTransportError, WAProviderError
from .factory import get_provider
from .schemas import (
    DeliveryStatus,
    InboundMessage,
    MessageType,
    SendResult,
    StatusUpdate,
)
from .webhook import (
    parse_cloudapi,
    parse_evolution,
    verify_cloudapi,
    verify_cloudapi_signature,
)

__version__ = "0.2.0"

__all__ = [
    "BaseProvider",
    "CloudAPIClient",
    "EvolutionClient",
    "get_provider",
    "SendResult",
    "InboundMessage",
    "StatusUpdate",
    "MessageType",
    "DeliveryStatus",
    "parse_cloudapi",
    "parse_evolution",
    "verify_cloudapi",
    "verify_cloudapi_signature",
    "WAProviderError",
    "ProviderAPIError",
    "ProviderTransportError",
]
