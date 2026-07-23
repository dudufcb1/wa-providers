"""Cliente WABA (WhatsApp Cloud API, oficial de Meta).

Analogia con Evolution: base_url = graph.facebook.com; "instancia" = phone_number_id;
"apikey" = access token (Bearer).
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, TypeVar

from .base import BaseProvider
from .exceptions import ProviderTransportError
from .http import PooledHTTPClient
from .schemas import (
    InstanceProfile,
    MediaDownload,
    SendResult,
    Template,
    TemplateCategory,
    TemplateStatus,
)

_POOL_KEYS = (
    "timeout",
    "max_connections",
    "max_keepalive",
    "max_retries",
    "backoff_base",
    "backoff_max",
)

LIST_MAX_ROWS = 10
LIST_ROW_TITLE_MAX = 24
LIST_ROW_DESCRIPTION_MAX = 72
LIST_ROW_ID_MAX = 200
BUTTONS_MAX = 3
BUTTON_ID_MAX = 256
BUTTON_TITLE_MAX = 20
HEADER_MAX = 60
INTERACTIVE_BODY_MAX = 1024

# Tope por pagina que acepta el catalogo de plantillas de Graph API.
TEMPLATES_PAGE_MAX = 250

# Tipos de media que acepta el endpoint de mensajes, y los que ademas admiten
# pie de foto (audio y sticker no lo llevan).
_CLOUD_MEDIA_TYPES = frozenset({"image", "video", "document", "audio", "sticker"})
_CLOUD_CAPTIONABLE = frozenset({"image", "video", "document"})

# Marcador de variable dentro del cuerpo de una plantilla: `{{1}}` en el formato
# posicional y `{{nombre}}` en el nombrado.
_TEMPLATE_VARIABLE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

logger = logging.getLogger(__name__)

# Enum de este paquete cuyo valor es la version en minusculas de lo que manda Meta.
_WireEnum = TypeVar("_WireEnum", bound=Enum)


def _required_text(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} no puede estar vacio")
    return value


def _visible_text(value: str | None, field: str, limit: int) -> str:
    text = _required_text(value, field).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _identifier(value: str | None, field: str, limit: int) -> str:
    identifier = _required_text(value, field)
    if identifier != identifier.strip():
        raise ValueError(f"{field} no puede tener espacios al inicio o al final")
    if len(identifier) > limit:
        raise ValueError(f"{field} no puede exceder {limit} caracteres")
    return identifier


def _enum_from_wire(raw: Any, enum: type[_WireEnum], fallback: _WireEnum) -> _WireEnum:
    """Traduce el valor de Meta (`"APPROVED"`) al enum del paquete (`"approved"`).

    Un estado o una categoria que Meta agregue despues no debe reventar la
    lectura del catalogo: cae al fallback y la plantilla se sigue listando.
    """
    if not isinstance(raw, str):
        return fallback
    try:
        return enum(raw.strip().lower())
    except ValueError:
        return fallback


def _template_body(components: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    """Saca el texto del componente BODY y los marcadores de variable que trae.

    Los marcadores se devuelven en orden de aparicion y sin repetir: es el orden
    en el que Meta espera los parametros al enviar la plantilla.
    """
    for component in components:
        if not isinstance(component, dict):
            continue
        if str(component.get("type", "")).upper() != "BODY":
            continue
        text = component.get("text")
        if not isinstance(text, str):
            return None, []
        seen: list[str] = []
        for match in _TEMPLATE_VARIABLE.finditer(text):
            name = match.group(1)
            if name not in seen:
                seen.append(name)
        return text, seen
    return None, []


def _next_cursor(data: dict[str, Any]) -> str | None:
    """Cursor de la siguiente pagina del catalogo, o None si ya no hay mas.

    Graph API manda `paging.next` (URL completa) solo mientras queden paginas, y
    `paging.cursors.after` incluso en la ultima. Seguir `after` sin mirar `next`
    haria un ciclo infinito pidiendo la misma pagina final una y otra vez.
    """
    paging = data.get("paging")
    if not isinstance(paging, dict) or not paging.get("next"):
        return None
    cursors = paging.get("cursors")
    if not isinstance(cursors, dict):
        return None
    after = cursors.get("after")
    return after if isinstance(after, str) and after else None


def _template(record: dict[str, Any]) -> Template:
    """Normaliza un nodo del catalogo de Graph API al modelo del paquete."""
    raw_components = record.get("components")
    components: list[dict[str, Any]] = []
    if isinstance(raw_components, list):
        components = [c for c in raw_components if isinstance(c, dict)]
    body, variables = _template_body(components)
    template_id = record.get("id")
    return Template(
        provider="cloudapi",
        id=template_id if isinstance(template_id, str) else None,
        name=str(record.get("name") or ""),
        language=str(record.get("language") or ""),
        status=_enum_from_wire(record.get("status"), TemplateStatus, TemplateStatus.UNKNOWN),
        category=_enum_from_wire(
            record.get("category"), TemplateCategory, TemplateCategory.UNKNOWN
        ),
        body=body,
        variables=variables,
        components=components,
        raw=record,
    )


def _result(data: dict[str, Any]) -> SendResult:
    msg = (data.get("messages") or [{}])[0]
    return SendResult(
        provider="cloudapi",
        message_id=msg.get("id"),
        accepted=bool(msg.get("id")),
        raw=data,
    )


class CloudAPIClient(BaseProvider):
    provider_name = "cloudapi"

    def __init__(
        self,
        token: str,
        phone_number_id: str,
        graph_version: str = "v21.0",
        waba_id: str | None = None,
        **pool: Any,
    ) -> None:
        self._token = token
        self.phone_number_id = phone_number_id
        # El catalogo de plantillas cuelga de la cuenta (WABA), no del numero, y
        # Meta no lo deriva de uno al otro: quien quiera leerlo tiene que darlo.
        # Enviar mensajes no lo necesita, por eso es opcional.
        self.waba_id = waba_id
        http = PooledHTTPClient(
            base_url=f"https://graph.facebook.com/{graph_version}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            **{k: pool[k] for k in _POOL_KEYS if k in pool},
        )
        super().__init__(http)

    @property
    def _messages_path(self) -> str:
        return f"/{self.phone_number_id}/messages"

    async def send_text(self, to: str, text: str, preview_url: bool = False) -> SendResult:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": text},
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def send_list(
        self,
        to: str,
        body: str,
        button_label: str,
        rows: list[dict[str, str]],
        header: str | None = None,
        section_title: str = "Opciones",
    ) -> SendResult:
        _required_text(to, "to")
        body_text = _visible_text(body, "body", INTERACTIVE_BODY_MAX)
        button_text = _visible_text(button_label, "button_label", BUTTON_TITLE_MAX)
        section_text = _visible_text(section_title, "section_title", LIST_ROW_TITLE_MAX)
        if not rows:
            raise ValueError("rows no puede estar vacio")
        if len(rows) > LIST_MAX_ROWS:
            logger.warning("send_list recorto %s filas al limite de %s", len(rows), LIST_MAX_ROWS)

        clean_rows: list[dict[str, str]] = []
        row_ids: set[str] = set()
        for index, row in enumerate(rows[:LIST_MAX_ROWS]):
            row_id = _identifier(
                row.get("id"),
                f"rows[{index}].id",
                LIST_ROW_ID_MAX,
            )
            if row_id in row_ids:
                raise ValueError("rows debe usar IDs unicos")
            row_ids.add(row_id)
            title = _visible_text(
                row.get("title"),
                f"rows[{index}].title",
                LIST_ROW_TITLE_MAX,
            )
            clean_row = {"id": row_id, "title": title}
            description = row.get("description")
            if isinstance(description, str) and description.strip():
                clean_row["description"] = _visible_text(
                    description,
                    f"rows[{index}].description",
                    LIST_ROW_DESCRIPTION_MAX,
                )
            clean_rows.append(clean_row)

        interactive: dict[str, Any] = {
            "type": "list",
            "body": {"text": body_text},
            "action": {
                "button": button_text,
                "sections": [{"title": section_text, "rows": clean_rows}],
            },
        }
        if header is not None and header.strip():
            interactive["header"] = {
                "type": "text",
                "text": _visible_text(header, "header", HEADER_MAX),
            }

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def send_buttons(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
    ) -> SendResult:
        _required_text(to, "to")
        body_text = _visible_text(body, "body", INTERACTIVE_BODY_MAX)
        if not buttons:
            raise ValueError("buttons no puede estar vacio")
        if len(buttons) > BUTTONS_MAX:
            logger.warning(
                "send_buttons recorto %s botones al limite de %s",
                len(buttons),
                BUTTONS_MAX,
            )

        clean_buttons: list[dict[str, Any]] = []
        button_ids: set[str] = set()
        for index, button in enumerate(buttons[:BUTTONS_MAX]):
            button_id = _identifier(
                button.get("id"),
                f"buttons[{index}].id",
                BUTTON_ID_MAX,
            )
            if button_id in button_ids:
                raise ValueError("buttons debe usar IDs unicos")
            button_ids.add(button_id)
            title = _visible_text(
                button.get("title"),
                f"buttons[{index}].title",
                BUTTON_TITLE_MAX,
            )
            clean_buttons.append(
                {
                    "type": "reply",
                    "reply": {"id": button_id, "title": title},
                }
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": clean_buttons},
            },
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def send_template(
        self,
        to: str,
        name: str,
        lang: str = "es_MX",
        body_params: list[Any] | None = None,
        components: list[dict[str, Any]] | None = None,
    ) -> SendResult:
        """Plantilla aprobada (unico camino para iniciar fuera de la ventana de 24h).

        Da `components` completos para casos con header/botones, o `body_params`
        para el caso simple de solo variables del cuerpo.
        """
        template: dict[str, Any] = {"name": name, "language": {"code": lang}}
        if components is not None:
            template["components"] = components
        elif body_params:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in body_params],
                }
            ]
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": template,
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def list_templates(
        self,
        *,
        status: str | None = None,
        language: str | None = None,
        limit: int = 100,
        max_pages: int = 10,
    ) -> list[Template]:
        """Catalogo de plantillas de la cuenta (WABA), ya normalizado.

        Es de solo lectura y necesita el permiso `whatsapp_business_management`,
        distinto del `whatsapp_business_messaging` con el que se envia; el token
        de sistema del alta suele traer los dos.

        `status` y `language` filtran del lado de Meta (p.ej. `status="APPROVED"`
        para quedarte solo con las enviables). El catalogo viene paginado por
        cursor: se siguen las paginas hasta `max_pages`, que existe para que una
        cuenta con cientos de plantillas no deje la peticion colgada.
        """
        waba_id = _required_text(self.waba_id, "waba_id")
        page_size = max(1, min(limit, TEMPLATES_PAGE_MAX))
        params: dict[str, Any] = {"limit": page_size}
        if status:
            params["status"] = status
        if language:
            params["language"] = language

        templates: list[Template] = []
        for _page in range(max(1, max_pages)):
            data = await self._http.request(
                "GET",
                f"/{waba_id}/message_templates",
                retry=True,
                params=params,
            )
            records = data.get("data")
            if not isinstance(records, list):
                break
            templates.extend(_template(r) for r in records if isinstance(r, dict))
            cursor = _next_cursor(data)
            if cursor is None or not records:
                break
            params = {**params, "after": cursor}
        return templates

    async def send_media(
        self,
        to: str,
        media: str,
        media_type: str = "document",
        mime_type: str | None = None,  # Cloud API lo deduce del archivo; se acepta por firma comun
        filename: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        """Manda media por su tipo real, para que WhatsApp la muestre como toca.

        Una imagen enviada como documento llega igual, pero se ve como un archivo
        adjunto en vez de mostrarse en el chat; por eso el tipo importa.

        `media` puede ser una URL publica (se manda como `link`) o el id de un
        archivo ya subido a Meta (se manda como `id`). El pie de foto solo lo
        aceptan imagen, video y documento: en audio y sticker se ignora, asi que
        el caller decide si lo manda como mensaje aparte.
        """
        _required_text(to, "to")
        _required_text(media, "media")
        _required_text(media_type, "media_type")
        if media_type not in _CLOUD_MEDIA_TYPES:
            raise ValueError(
                f"media_type invalido: {media_type!r}. "
                f"Validos: {', '.join(sorted(_CLOUD_MEDIA_TYPES))}"
            )
        reference = "link" if media.startswith(("http://", "https://")) else "id"
        content: dict[str, Any] = {reference: media}
        if filename and media_type == "document":
            content["filename"] = filename
        if caption and media_type in _CLOUD_CAPTIONABLE:
            content["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": media_type,
            media_type: content,
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def send_document(
        self,
        to: str,
        *,
        link: str | None = None,
        media_id: str | None = None,
        filename: str | None = None,
        caption: str | None = None,
    ) -> SendResult:
        document: dict[str, Any] = {}
        if media_id:
            document["id"] = media_id
        elif link:
            document["link"] = link
        else:
            raise ValueError("send_document requiere link o media_id")
        if filename:
            document["filename"] = filename
        if caption:
            document["caption"] = caption
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": document,
        }
        return _result(
            await self._http.request("POST", self._messages_path, retry=False, json=payload)
        )

    async def mark_read(self, message_id: str) -> dict[str, Any]:
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
        return await self._http.request("POST", self._messages_path, retry=True, json=payload)

    async def fetch_profile(self, phone_number_id: str | None = None) -> InstanceProfile:
        """Telefono y nombre verificado del numero, para mostrarlos en pantalla.

        Es el equivalente del `fetch_profile` de Evolution: deja enseñar el numero
        real en vez del identificador interno. De paso sirve para comprobar que el
        token funciona y que el numero existe, que es lo que se necesita al darlo
        de alta."""
        target = _required_text(phone_number_id or self.phone_number_id, "phone_number_id")
        data = await self._http.request(
            "GET",
            f"/{target}",
            retry=True,
            params={"fields": "display_phone_number,verified_name"},
        )
        phone = data.get("display_phone_number")
        name = data.get("verified_name")
        return InstanceProfile(
            phone=phone if isinstance(phone, str) and phone else None,
            profile_name=name if isinstance(name, str) and name else None,
        )

    async def health(self) -> dict[str, Any]:
        """health_status del numero: el mejor diagnostico cuando algo no llega."""
        return await self._http.request(
            "GET", f"/{self.phone_number_id}", params={"fields": "health_status"}
        )

    async def get_media(self, media_id: str) -> MediaDownload:
        media_id = _required_text(media_id, "media_id")
        metadata = await self._http.request(
            "GET",
            f"/{media_id}",
            params={"phone_number_id": self.phone_number_id},
        )
        media_url = metadata.get("url")
        if not isinstance(media_url, str) or not media_url.strip():
            raise ProviderTransportError(
                "Cloud API no devolvio una URL de descarga",
                body=metadata,
            )

        downloaded = await self._http.request_bytes(
            "GET",
            media_url,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        mime_type = metadata.get("mime_type") or downloaded.headers.get("content-type")
        filename = metadata.get("filename")
        return MediaDownload(
            provider="cloudapi",
            content=downloaded.content,
            base64=None,
            mime_type=mime_type if isinstance(mime_type, str) else None,
            filename=filename if isinstance(filename, str) else None,
            raw=metadata,
        )
