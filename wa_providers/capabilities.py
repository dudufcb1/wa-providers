"""Contratos estructurales para capacidades opcionales de cada proveedor."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .schemas import MediaDownload, SendResult


@runtime_checkable
class TextSender(Protocol):
    async def send_text(self, to: str, text: str) -> SendResult: ...


@runtime_checkable
class TemplateSender(Protocol):
    async def send_template(
        self,
        to: str,
        name: str,
        lang: str = "es_MX",
        body_params: list[Any] | None = None,
        components: list[dict[str, Any]] | None = None,
    ) -> SendResult: ...


@runtime_checkable
class InteractiveSender(Protocol):
    async def send_list(
        self,
        to: str,
        body: str,
        button_label: str,
        rows: list[dict[str, str]],
        header: str | None = None,
        section_title: str = "Opciones",
    ) -> SendResult: ...

    async def send_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
    ) -> SendResult: ...


@runtime_checkable
class CloudMediaDownloader(Protocol):
    async def get_media(self, media_id: str) -> MediaDownload: ...


@runtime_checkable
class ReadMarker(Protocol):
    async def mark_read(self, message_id: str) -> dict[str, Any]: ...


@runtime_checkable
class HealthChecker(Protocol):
    async def health(self) -> dict[str, Any]: ...


@runtime_checkable
class GenericMediaSender(Protocol):
    async def send_media(
        self,
        to: str,
        media: str,
        media_type: str = "document",
        mime_type: str | None = None,
        filename: str | None = None,
        caption: str | None = None,
    ) -> SendResult: ...


@runtime_checkable
class EvolutionMediaDownloader(Protocol):
    async def get_media_base64(
        self,
        message: dict[str, Any],
        convert_to_mp4: bool = False,
    ) -> MediaDownload: ...


@runtime_checkable
class WebhookConfigurator(Protocol):
    async def set_webhook(
        self,
        url: str,
        events: list[str] | None = None,
        *,
        enabled: bool = True,
        by_events: bool = False,
        include_base64: bool = False,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...
