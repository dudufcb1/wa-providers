"""Armado de los payloads interactivos de Evolution (botones y listas).

Está aparte del cliente a propósito: aquí no hay HTTP ni estado, solo la
traducción del contrato común (`InteractiveSender`) a la forma que esperan
`/message/sendButtons` y `/message/sendList`. Así se puede probar el payload sin
levantar nada.

Ojo con lo que NO es igual al canal oficial: Evolution acepta botones de enlace,
llamada, copiar y PIX en un mensaje libre, cosa que Meta solo permite dentro de
una plantilla aprobada. Y manda dos sabores de lista (ver `native_flow`).
"""

from __future__ import annotations

from typing import Any

from .interactive import (
    BUTTON_ID_MAX,
    BUTTON_TITLE_MAX,
    BUTTONS_MAX,
    FOOTER_MAX,
    HEADER_MAX,
    INTERACTIVE_BODY_MAX,
    LIST_MAX_ROWS,
    LIST_ROW_DESCRIPTION_MAX,
    LIST_ROW_ID_MAX,
    LIST_ROW_TITLE_MAX,
    identifier,
    optional_text,
    required_text,
    visible_text,
)

# Los cinco tipos que dibuja WhatsApp en un mensaje interactivo. `reply` es el
# único que existe también en el canal oficial fuera de plantilla.
BUTTON_TYPES = frozenset({"reply", "url", "call", "copy", "pix"})

# Campo obligatorio de cada tipo, además del texto que se ve en el botón.
_BUTTON_FIELDS: dict[str, str] = {
    "url": "url",
    "call": "phone",
    "copy": "code",
}


def _button_type(raw: Any, index: int) -> str:
    """Normaliza el tipo de un botón; sin tipo se asume `reply`, que es el común."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return "reply"
    if not isinstance(raw, str) or raw.strip().lower() not in BUTTON_TYPES:
        raise ValueError(
            f"buttons[{index}].type inválido: {raw!r}. "
            f"Válidos: {', '.join(sorted(BUTTON_TYPES))}"
        )
    return raw.strip().lower()


def _check_button_mix(types: list[str]) -> None:
    """Aplica las reglas de mezcla que WhatsApp impone y Evolution rechaza con 400.

    Se validan aquí para que el error salga antes de la llamada y diga qué pasó,
    en vez de llegar como un 400 con el texto en inglés del motor.
    """
    if "pix" in types:
        if len(types) > 1:
            raise ValueError("el botón de PIX no se puede combinar con otros botones")
        return
    if "reply" in types and any(kind != "reply" for kind in types):
        raise ValueError(
            "los botones de respuesta no se pueden mezclar con enlace, llamada o copiar"
        )
    if len(types) > BUTTONS_MAX:
        raise ValueError(f"no se pueden mandar más de {BUTTONS_MAX} botones")


def _pix_button(button: dict[str, str], index: int) -> dict[str, Any]:
    """Botón de pago PIX (Brasil). Lleva sus propios campos, no `displayText`."""
    return {
        "type": "pix",
        "currency": (button.get("currency") or "BRL").strip(),
        "name": required_text(button.get("name"), f"buttons[{index}].name").strip(),
        "keyType": required_text(button.get("key_type"), f"buttons[{index}].key_type").strip(),
        "key": required_text(button.get("key"), f"buttons[{index}].key").strip(),
    }


def _button(button: dict[str, str], index: int, kind: str, seen_ids: set[str]) -> dict[str, Any]:
    """Traduce un botón nuestro al objeto que espera Evolution."""
    if kind == "pix":
        return _pix_button(button, index)

    entry: dict[str, Any] = {
        "type": kind,
        "displayText": visible_text(
            button.get("title"),
            f"buttons[{index}].title",
            BUTTON_TITLE_MAX,
        ),
    }
    if kind == "reply":
        button_id = identifier(button.get("id"), f"buttons[{index}].id", BUTTON_ID_MAX)
        if button_id in seen_ids:
            raise ValueError("buttons debe usar IDs únicos")
        seen_ids.add(button_id)
        entry["id"] = button_id
        return entry

    # Enlace, llamada y copiar no regresan un id: lo que importa es su destino.
    field = _BUTTON_FIELDS[kind]
    wire = {"url": "url", "call": "phoneNumber", "copy": "copyCode"}[kind]
    entry[wire] = required_text(button.get(field), f"buttons[{index}].{field}").strip()
    return entry


def buttons_payload(
    to: str,
    body: str,
    buttons: list[dict[str, str]],
    *,
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Payload de `/message/sendButtons`.

    Evolution arma el cuerpo como `*title*` y debajo `description`. Por eso, con
    `header`, el encabezado va en negritas y el cuerpo debajo en texto normal; sin
    `header`, el cuerpo entero sale en negritas, que es como se ve un mensaje de
    botones de Evolution por omisión.
    """
    required_text(to, "to")
    body_text = visible_text(body, "body", INTERACTIVE_BODY_MAX)
    if not buttons:
        raise ValueError("buttons no puede estar vacío")

    kinds = [_button_type(button.get("type"), index) for index, button in enumerate(buttons)]
    _check_button_mix(kinds)

    seen_ids: set[str] = set()
    wire_buttons = [
        _button(button, index, kinds[index], seen_ids) for index, button in enumerate(buttons)
    ]

    head = optional_text(header, "header", HEADER_MAX)
    payload: dict[str, Any] = {
        "number": to,
        "title": head or body_text,
        "buttons": wire_buttons,
    }
    if head:
        payload["description"] = body_text
    foot = optional_text(footer, "footer", FOOTER_MAX)
    if foot:
        payload["footer"] = foot
    return payload


def _rows_by_section(
    rows: list[dict[str, str]],
    default_section: str,
) -> list[dict[str, Any]]:
    """Agrupa las filas en secciones, respetando el orden en que llegaron.

    El contrato común solo tiene una lista plana de filas; Evolution sí admite
    varias secciones. Para no partir la firma, cada fila puede traer `section` y
    aquí se agrupan; las que no la traen caen en la sección de omisión.
    """
    sections: list[dict[str, Any]] = []
    index_by_title: dict[str, int] = {}
    seen_ids: set[str] = set()

    for index, row in enumerate(rows[:LIST_MAX_ROWS]):
        row_id = identifier(row.get("id"), f"rows[{index}].id", LIST_ROW_ID_MAX)
        if row_id in seen_ids:
            raise ValueError("rows debe usar IDs únicos")
        seen_ids.add(row_id)

        wire_row: dict[str, str] = {
            "title": visible_text(row.get("title"), f"rows[{index}].title", LIST_ROW_TITLE_MAX),
            "rowId": row_id,
        }
        description = optional_text(
            row.get("description"),
            f"rows[{index}].description",
            LIST_ROW_DESCRIPTION_MAX,
        )
        # Evolution manda `description` siempre; la moderna además exige que no
        # venga vacía, así que se rellena con el título antes que omitirla.
        wire_row["description"] = description or ""

        title = optional_text(row.get("section"), f"rows[{index}].section", LIST_ROW_TITLE_MAX)
        title = title or default_section
        position = index_by_title.get(title)
        if position is None:
            index_by_title[title] = len(sections)
            sections.append({"title": title, "rows": [wire_row]})
        else:
            sections[position]["rows"].append(wire_row)

    return sections


def list_payload(
    to: str,
    body: str,
    button_label: str,
    rows: list[dict[str, str]],
    header: str | None = None,
    section_title: str = "Opciones",
    *,
    footer: str | None = None,
    native_flow: bool = False,
) -> dict[str, Any]:
    """Payload de `/message/sendList`.

    `native_flow=True` manda la lista MODERNA, que solo se ve en el teléfono. Por
    omisión va la CLÁSICA, que además de en el teléfono se ve en WhatsApp Web —
    por eso es la de omisión aunque la moderna se vea mejor.
    """
    required_text(to, "to")
    body_text = visible_text(body, "body", INTERACTIVE_BODY_MAX)
    label = visible_text(button_label, "button_label", BUTTON_TITLE_MAX)
    default_section = visible_text(section_title, "section_title", LIST_ROW_TITLE_MAX)
    if not rows:
        raise ValueError("rows no puede estar vacío")

    payload: dict[str, Any] = {
        "number": to,
        "title": optional_text(header, "header", HEADER_MAX) or "",
        "description": body_text,
        "buttonText": label,
        "sections": _rows_by_section(rows, default_section),
    }
    foot = optional_text(footer, "footer", FOOTER_MAX)
    if foot:
        payload["footerText"] = foot
    if native_flow:
        payload["nativeFlow"] = True
    return payload
