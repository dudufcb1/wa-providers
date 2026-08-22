"""Botones y listas por el canal no oficial (Evolution parchada).

Se prueban aparte de `test_clients.py` porque son una capacidad opcional: existen
en el cliente pero nacen apagadas, y la mitad de lo que hay que cuidar es el
armado del payload, que no necesita ni cliente ni HTTP.
"""

from __future__ import annotations

from typing import Any

import pytest

import wa_providers.evolution as evolution_module
from wa_providers import EvolutionClient, ProviderAPIError, get_provider
from wa_providers.capabilities import InteractiveSender
from wa_providers.evolution_interactive import buttons_payload, list_payload

from test_clients import StubHTTPClient


def _client(monkeypatch: pytest.MonkeyPatch, http: StubHTTPClient, **kwargs: Any) -> EvolutionClient:
    """Arma un cliente de Evolution con el HTTP falseado."""
    monkeypatch.setattr(evolution_module, "PooledHTTPClient", lambda **_: http)
    return EvolutionClient(
        base_url="https://evolution.example.test",
        api_key="evolution-key",
        instance="recall-sales",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_interactive_is_off_unless_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una Evolution sin parchar acepta el envío y WhatsApp lo descarta en silencio.

    Por eso el cliente nace con los interactivos apagados y avisa en vez de mandar:
    quien no tenga el parche no debe poder tirar mensajes al vacío sin enterarse.
    """
    http = StubHTTPClient({"key": {"id": "no-deberia-usarse"}})
    client = _client(monkeypatch, http)

    assert client.supports_interactive is False
    with pytest.raises(ProviderAPIError):
        await client.send_buttons("5215550000001", "¿Confirmas?", [{"id": "si", "title": "Sí"}])
    with pytest.raises(ProviderAPIError):
        await client.send_list(
            "5215550000001",
            "Elige",
            "Ver opciones",
            [{"id": "a", "title": "A"}],
        )
    assert http.calls == []
    await client.aclose()


def test_the_factory_carries_the_interactive_switch() -> None:
    """El interruptor se puede prender desde el config, que es como lo arma la app."""
    plain = get_provider(
        {
            "provider": "evolution",
            "base_url": "https://evolution.example.test",
            "api_key": "k",
            "instance": "recall-sales",
        }
    )
    patched = get_provider(
        {
            "provider": "evolution",
            "base_url": "https://evolution.example.test",
            "api_key": "k",
            "instance": "recall-sales",
            "interactive": True,
        }
    )
    assert isinstance(plain, EvolutionClient) and plain.supports_interactive is False
    assert isinstance(patched, EvolutionClient) and patched.supports_interactive is True
    # El protocolo solo mira que los metodos existan: por eso no sirve para saber
    # si estan encendidos, y hay que preguntar por `supports_interactive`.
    assert isinstance(plain, InteractiveSender)


@pytest.mark.asyncio
async def test_reply_buttons_travel_to_the_patched_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con el interruptor prendido, los botones de respuesta salen por sendButtons.

    Sin `header`, el cuerpo va en `title` porque Evolution lo imprime en negritas
    arriba y no hay nada más que poner ahí.
    """
    http = StubHTTPClient({"key": {"id": "evolution-buttons-id"}})
    client = _client(monkeypatch, http, interactive=True)

    result = await client.send_buttons(
        "5215550000001",
        "¿Confirmas tu cita del jueves?",
        [
            {"id": "confirma", "title": "Sí, confirmo"},
            {"id": "cambia", "title": "Cambiar hora"},
        ],
        footer="Clínica del Valle",
    )

    assert http.calls == [
        {
            "method": "POST",
            "path": "/message/sendButtons/recall-sales",
            "retry": False,
            "json": {
                "number": "5215550000001",
                "title": "¿Confirmas tu cita del jueves?",
                "footer": "Clínica del Valle",
                "buttons": [
                    {"type": "reply", "displayText": "Sí, confirmo", "id": "confirma"},
                    {"type": "reply", "displayText": "Cambiar hora", "id": "cambia"},
                ],
            },
        }
    ]
    assert result.message_id == "evolution-buttons-id"
    assert result.accepted is True
    await client.aclose()


def test_a_header_pushes_the_body_below_the_title() -> None:
    """Con `header`, el encabezado va en negritas y el cuerpo queda debajo."""
    payload = buttons_payload(
        "5215550000001",
        "Tenemos lugar el jueves a las 10:00.",
        [{"id": "ok", "title": "Va"}],
        header="Cita disponible",
    )
    assert payload["title"] == "Cita disponible"
    assert payload["description"] == "Tenemos lugar el jueves a las 10:00."


def test_link_call_and_copy_buttons_carry_their_destination() -> None:
    """Los tres tipos que el canal oficial solo permite dentro de plantilla.

    Ninguno regresa un id: lo que importa es a dónde llevan, y por eso cada uno
    manda su campo propio.
    """
    payload = buttons_payload(
        "5215550000001",
        "Aquí están los datos de tu pedido.",
        [
            {"type": "url", "title": "Ver pedido", "url": "https://ejemplo.mx/p/1"},
            {"type": "call", "title": "Llamar", "phone": "+525512345678"},
            {"type": "copy", "title": "Copiar folio", "code": "MX-4471"},
        ],
    )
    assert payload["buttons"] == [
        {"type": "url", "displayText": "Ver pedido", "url": "https://ejemplo.mx/p/1"},
        {"type": "call", "displayText": "Llamar", "phoneNumber": "+525512345678"},
        {"type": "copy", "displayText": "Copiar folio", "copyCode": "MX-4471"},
    ]


def test_mixing_reply_with_other_kinds_is_refused_before_sending() -> None:
    """WhatsApp no dibuja respuesta y enlace en el mismo mensaje; Evolution da 400.

    Se corta antes de la llamada para que el error salga en español y diga qué pasó.
    """
    with pytest.raises(ValueError, match="no se pueden mezclar"):
        buttons_payload(
            "5215550000001",
            "Elige",
            [
                {"id": "si", "title": "Sí"},
                {"type": "url", "title": "Ver", "url": "https://ejemplo.mx"},
            ],
        )


def test_more_than_three_buttons_is_refused() -> None:
    """El tope de tres es de WhatsApp; el cuarto botón no se dibujaría."""
    with pytest.raises(ValueError, match="más de 3"):
        buttons_payload(
            "5215550000001",
            "Elige",
            [{"type": "url", "title": f"B{n}", "url": "https://ejemplo.mx"} for n in range(4)],
        )


def test_repeated_reply_ids_are_refused() -> None:
    """Dos botones con el mismo id harían imposible saber cuál picó el contacto."""
    with pytest.raises(ValueError, match="IDs únicos"):
        buttons_payload(
            "5215550000001",
            "Elige",
            [{"id": "x", "title": "Uno"}, {"id": "x", "title": "Otro"}],
        )


@pytest.mark.asyncio
async def test_the_classic_list_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Por omisión va la lista clásica: es la única que se ve en WhatsApp Web.

    La moderna se ve mejor pero solo en el teléfono, así que no puede ser la de
    omisión: en la bandeja del CRM se vería un mensaje vacío.
    """
    http = StubHTTPClient({"key": {"id": "evolution-list-id"}})
    client = _client(monkeypatch, http, interactive=True)

    await client.send_list(
        "5215550000001",
        "Elige el servicio",
        "Ver opciones",
        [
            {"id": "primera", "title": "Primera vez", "description": "45 min"},
            {"id": "seguimiento", "title": "Seguimiento"},
        ],
        section_title="Consultas",
    )

    payload = http.calls[0]["json"]
    assert http.calls[0]["path"] == "/message/sendList/recall-sales"
    assert "nativeFlow" not in payload
    assert payload["buttonText"] == "Ver opciones"
    assert payload["description"] == "Elige el servicio"
    assert payload["sections"] == [
        {
            "title": "Consultas",
            "rows": [
                {"title": "Primera vez", "rowId": "primera", "description": "45 min"},
                {"title": "Seguimiento", "rowId": "seguimiento", "description": ""},
            ],
        }
    ]
    await client.aclose()


def test_rows_can_declare_their_own_section() -> None:
    """El contrato común solo pasa filas planas, así que la sección viaja en la fila.

    Se respeta el orden de aparición para que el menú se lea como se escribió.
    """
    payload = list_payload(
        "5215550000001",
        "Elige",
        "Ver",
        [
            {"id": "a", "title": "Primera vez", "section": "Consultas"},
            {"id": "b", "title": "Radiografía", "section": "Estudios"},
            {"id": "c", "title": "Seguimiento", "section": "Consultas"},
        ],
    )
    assert [section["title"] for section in payload["sections"]] == ["Consultas", "Estudios"]
    assert [row["rowId"] for row in payload["sections"][0]["rows"]] == ["a", "c"]


def test_the_modern_list_is_opt_in() -> None:
    """`native_flow=True` es lo único que cambia entre las dos listas del motor."""
    payload = list_payload(
        "5215550000001",
        "Elige",
        "Ver",
        [{"id": "a", "title": "Uno"}],
        native_flow=True,
    )
    assert payload["nativeFlow"] is True


def test_an_empty_list_is_refused() -> None:
    """Un menú sin filas llegaría como un mensaje que no se puede abrir."""
    with pytest.raises(ValueError, match="rows no puede estar vacío"):
        list_payload("5215550000001", "Elige", "Ver", [])


def test_long_visible_texts_are_trimmed_but_ids_are_not() -> None:
    """El texto se recorta porque WhatsApp lo cortaría igual; el id nunca se toca.

    Recortar un id rompería el macheo con lo que el sistema de arriba guardó, así
    que pasarse del tope revienta en vez de alterarlo.
    """
    payload = list_payload(
        "5215550000001",
        "Elige",
        "Ver",
        [{"id": "a" * 200, "title": "T" * 40}],
    )
    row = payload["sections"][0]["rows"][0]
    assert row["rowId"] == "a" * 200
    assert len(row["title"]) == 24 and row["title"].endswith("…")

    with pytest.raises(ValueError, match="no puede exceder"):
        list_payload("5215550000001", "Elige", "Ver", [{"id": "a" * 201, "title": "T"}])
