"""Contratos estructurales para capacidades opcionales de cada proveedor."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .schemas import InstanceProfile, MediaDownload, SendResult, Template


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
class TemplateCatalog(Protocol):
    """Lectura del catalogo de plantillas de la cuenta.

    Solo aplica a los motores donde las plantillas son un asset del proveedor
    (Cloud API). Evolution no la implementa: al mandar por WhatsApp no oficial no
    hay plantillas que aprobar ni catalogo que consultar.
    """

    async def list_templates(
        self,
        *,
        status: str | None = None,
        language: str | None = None,
        limit: int = 100,
        max_pages: int = 10,
    ) -> list[Template]: ...


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
class WabaWebhookSubscriber(Protocol):
    """Suscripcion de la app a los eventos de una cuenta, con URL propia opcional.

    Solo aplica a Cloud API: es lo que deja dar de alta la cuenta de un cliente
    sin que nadie entre al panel de Meta a escribir la URL a mano.
    """

    async def subscribe_waba_webhook(
        self,
        callback_url: str | None = None,
        verify_token: str | None = None,
        waba_id: str | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class ProfileReader(Protocol):
    """Lectura del telefono y el nombre con el que se presenta un numero.

    Lo implementan los dos motores, cada uno con su identificador: el nombre de
    la instancia en Evolution y el `phone_number_id` en Cloud API.
    """

    # Posicional a proposito (`/`): cada motor nombra distinto lo que identifica al
    # numero, y aqui lo unico que importa es que se pueda pedir sin argumentos.
    async def fetch_profile(self, target: str | None = None, /) -> InstanceProfile: ...


@runtime_checkable
class VoiceNoteSender(Protocol):
    """Nota de voz (PTT), que se reproduce con su onda en vez de bajarse como archivo.

    Es un envio aparte porque no todos los motores lo distinguen del audio comun.
    """

    async def send_whatsapp_audio(self, to: str, audio: str) -> SendResult: ...


@runtime_checkable
class EvolutionMediaDownloader(Protocol):
    async def get_media_base64(
        self,
        message: dict[str, Any],
        convert_to_mp4: bool = False,
    ) -> MediaDownload: ...


@runtime_checkable
class InstanceManager(Protocol):
    """Alta y vinculacion de numeros, para motores que las administran.

    Cloud API no la implementa: ahi el numero se da de alta en Meta, no por API.
    """

    async def create_instance(
        self,
        instance_name: str,
        *,
        integration: str = "WHATSAPP-BAILEYS",
        with_qr: bool = True,
    ) -> dict[str, Any]: ...

    async def connect(self, instance_name: str | None = None) -> dict[str, Any]: ...

    async def connection_state(self, instance_name: str | None = None) -> str | None: ...

    async def logout_instance(self, instance_name: str | None = None) -> dict[str, Any]: ...

    async def delete_instance(self, instance_name: str | None = None) -> dict[str, Any]: ...

    async def fetch_profile(self, instance_name: str | None = None) -> InstanceProfile: ...


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
