"""Limites y validaciones de los mensajes interactivos (botones y listas).

Viven aparte porque los dos motores mandan lo mismo por caminos distintos: Cloud
API con un objeto `interactive` y Evolution con `/message/sendButtons` y
`/message/sendList`. Los topes NO son de Meta sino de WhatsApp (los aplica la app
del que recibe), asi que valen igual para el canal oficial y para el no oficial:
un titulo de boton de 30 caracteres se corta en pantalla en los dos.
"""

from __future__ import annotations

LIST_MAX_ROWS = 10
LIST_ROW_TITLE_MAX = 24
LIST_ROW_DESCRIPTION_MAX = 72
LIST_ROW_ID_MAX = 200
BUTTONS_MAX = 3
BUTTON_ID_MAX = 256
BUTTON_TITLE_MAX = 20
HEADER_MAX = 60
INTERACTIVE_BODY_MAX = 1024
FOOTER_MAX = 60


def required_text(value: str | None, field: str) -> str:
    """Exige un texto con algo adentro; `None`, vacio o solo espacios revientan."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} no puede estar vacio")
    return value


def visible_text(value: str | None, field: str, limit: int) -> str:
    """Texto que ve el cliente: se recorta al tope y se marca con puntos suspensivos.

    Se recorta en vez de reventar porque un cuerpo largo de mas no es un error del
    que manda: WhatsApp lo cortaria igual, y perder el envio seria peor.
    """
    text = required_text(value, field).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def optional_text(value: str | None, field: str, limit: int) -> str | None:
    """Como `visible_text` pero deja pasar el `None` y el vacio sin quejarse."""
    if value is None or not value.strip():
        return None
    return visible_text(value, field, limit)


def identifier(value: str | None, field: str, limit: int) -> str:
    """Identificador que regresa en la respuesta del cliente: nunca se altera.

    A diferencia del texto visible, aqui pasarse del tope revienta: recortar un id
    romperia el macheo con lo que el sistema de arriba guardo.
    """
    ident = required_text(value, field)
    if ident != ident.strip():
        raise ValueError(f"{field} no puede tener espacios al inicio o al final")
    if len(ident) > limit:
        raise ValueError(f"{field} no puede exceder {limit} caracteres")
    return ident
