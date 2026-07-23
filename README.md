# wa-providers

> **Esto es un proyecto base (blueprint). No se construye encima de él.**
>
> Cada proyecto que necesite WhatsApp **parte de aquí**: se copia esta base y se
> adapta al dominio de ese proyecto. Lo que NO se hace es acoplar este repo a un
> proyecto concreto (su CRM, su base de datos, su modelo de negocio) ni volverlo
> una dependencia compartida que varios proyectos van jalando y modificando.
>
> Regla práctica:
>
> - Si el cambio sirve para **cualquiera** que hable con WhatsApp (un tipo de
>   mensaje que faltaba, un bug del parser, un endpoint del proveedor) → va aquí.
> - Si el cambio huele a **un** proyecto (mapear a un contacto de tu CRM,
>   normalizar teléfonos de un país, tu esquema de base de datos, tus reglas de
>   negocio) → va en ese proyecto, no aquí.
>
> Por eso el paquete no trae rutas HTTP, ni persistencia, ni configuración por
> variables de entorno: son decisiones de cada proyecto.

WhatsApp agnóstico detrás de una interfaz común. Un solo código de envío en tu app,
dos motores intercambiables por debajo:

- **cloudapi** — WhatsApp Cloud API oficial de Meta (WABA).
- **evolution** — Evolution API (WhatsApp Web / Baileys).

Cambias de motor con **una línea de config**. Nace listo para volumen: cliente
`httpx` persistente con pool de conexiones + reintentos con backoff de fábrica.

## Instalar

Desde el checkout local:

```bash
pip install .
```

## Enviar (mismo código para ambos motores)

```python
from wa_providers import get_provider

# Solo cambia esta config para saltar de un motor al otro:
config = {
    "provider": "cloudapi",
    "token": "EAAG...",
    "phone_number_id": "1282771931587897",
    # opcionales de pool/reintentos para operaciones idempotentes:
    "max_retries": 3, "timeout": 20.0,
}
# config = {"provider": "evolution", "base_url": "...", "api_key": "...", "instance": "..."}

async def demo():
    async with get_provider(config) as wa:
        res = await wa.send_text("5215512345678", "Hola")
        print(res.accepted, res.message_id)
```

Iniciar fuera de la ventana de 24h (solo Cloud API): `send_template(...)`.

```python
await wa.send_template("5215512345678", "mi_plantilla", lang="es_MX", body_params=["Eduardo"])
```

Para saber **qué plantillas** hay aprobadas antes de mandar una, `list_templates(...)`
(solo Cloud API). Cuelga de la cuenta (WABA), no del número, así que el cliente se
construye con `waba_id`, y el token necesita el permiso `whatsapp_business_management`
(distinto del `whatsapp_business_messaging` con el que se envía; el token de sistema
del alta suele traer los dos).

```python
config = {
    "provider": "cloudapi",
    "token": "EAAG...",
    "phone_number_id": "1234567890",
    "waba_id": "9876543210",
}
async with get_provider(config) as wa:
    for t in await wa.list_templates(status="APPROVED"):
        print(t.name, t.language, t.category.value, t.variables)
        # -> recordatorio_cita es_MX utility ['1', '2']
```

Cada `Template` trae el texto del cuerpo y `variables` con los marcadores en el
orden en que Meta espera los parámetros, que es justo lo que necesita una pantalla
para pedirlos. El catálogo viene paginado por cursor; el recorrido se detiene en la
última página o al llegar a `max_pages`.

## Recibir (webhook, framework-agnóstico)

La **ruta** la pone tu app; el paquete solo parsea/verifica.

```python
from wa_providers import parse_cloudapi, verify_cloudapi, verify_cloudapi_signature

# GET de verificacion de Meta:
challenge = verify_cloudapi(request_query_params, verify_token="mi_token")
# -> si es str, responde texto plano 200; si None, 403

# POST: valida SIEMPRE la firma contra el body crudo antes de parsear JSON:
signature_ok = verify_cloudapi_signature(
    raw_body,
    request_headers.get("X-Hub-Signature-256"),
    app_secret="mi_app_secret",
)

# POST con eventos:
messages, statuses = parse_cloudapi(payload)   # listas ya normalizadas
for m in messages:
    print(m.from_number, m.type, m.text)
for s in statuses:
    print(s.message_id, s.status)   # sent/delivered/read/failed
```

Para Evolution: `parse_evolution(payload)`. Los eventos `MESSAGES_UPDATE` se
normalizan por separado con `parse_evolution_status(payload)`. El mensaje conserva
`sender_name`, `from_me`, `is_group`, `remote_jid` y media tipada. Las selecciones
interactivas se reducen a `type`, `id` y `title` en ambos motores. Cada parser de
Evolution acepta solo su tipo de evento, para que un status no entre al flujo como
mensaje.

### Qué descarta el parser de Evolution (y por qué)

La identidad del remitente se valida antes de construir el mensaje. Se prefiere
descartar a fabricar un `from_number` que no es un teléfono, porque ese valor
suele terminar creando registros basura en el sistema de destino:

- **`@lid` irresoluble.** WhatsApp multi-dispositivo entrega identificadores
  opacos; se intenta `remoteJidAlt` y luego `senderPn`. Si ninguno da un número
  real, el mensaje se descarta.
- **Difusión y canales.** `status@broadcast` y `@newsletter` no son
  conversaciones con una persona.
- **Mensajes sin `key.id`.** Sin id no hay forma de deduplicar ni de
  correlacionar el estado de entrega después.

**Grupos (`@g.us`) sí se procesan**, pero `remoteJid` identifica al grupo, no a
quien escribió. El autor real se toma de `key.participant` (resolviendo su `@lid`
si hace falta), `is_group` queda en `True` y `remote_jid` conserva el JID del
grupo para poder responder ahí. Si el participante no se puede resolver, se
descarta.

## Capacidades especificas

El contrato comun se mantiene en `send_text` y `send_document`. Las funciones que
solo existen en un proveedor se exponen mediante Protocols comprobables en runtime:

- Cloud API: `TemplateSender`, `TemplateCatalog`, `InteractiveSender`,
  `GenericMediaSender`, `CloudMediaDownloader`, `ReadMarker` y `HealthChecker`.
- Evolution: `GenericMediaSender`, `VoiceNoteSender`, `EvolutionMediaDownloader`,
  `WebhookConfigurator` e `InstanceManager`.
- Los dos: `TextSender` y `ProfileReader` (`fetch_profile`, para saber con qué
  número se presenta cada uno).

```python
from wa_providers import InteractiveSender

if isinstance(wa, InteractiveSender):
    await wa.send_buttons(
        "5215512345678",
        "Elige una opcion",
        [{"id": "continue", "title": "Continuar"}],
    )
```

`CloudAPIClient.get_media(media_id)` devuelve bytes y metadata tipada. Evolution
acepta el objeto completo del webhook o la forma minima con `key.id` que la API usa
para recuperar el mensaje almacenado:

```python
download = await evolution.get_media_base64(inbound.raw["data"])
```

`EvolutionClient.set_webhook(...)` usa el contrato anidado de Evolution API 2.3.7
con `enabled`, `byEvents`, `base64` y `events` dentro de `webhook`.

Los flujos conversacionales son opcionales. Un proyecto puede usar este paquete
solo para CRM o atencion manual; cuando necesita menus o agentes, Waflow consume
estos mismos mensajes y capacidades sin crear un segundo cliente de WhatsApp.

## Qué va en el paquete y qué en tu app

- **Paquete (framework-free):** clientes, esquemas normalizados, factory, parsers/verify de webhook, pooling + retry/backoff.
- **Tu app (por proyecto):** la ruta del webhook, guardar en tu DB, la UI, y —a escala— la cola + workers que consumen los envíos respetando los rate limits de Meta.

### Lo que el paquete deliberadamente NO hace

Cuatro cosas que todo proyecto va a necesitar y que no están aquí porque dependen
del dominio. Vale la pena tenerlas presentes antes de partir de esta base:

1. **Normalizar teléfonos.** Los números salen tal como los entrega el
   proveedor. En México eso muerde: Baileys devuelve el JID con el `1` móvil
   (`521...`) pero acepta enviar sin él (`52...`), y la mayoría de los CRM
   guardan E.164 (`+52...`). Sin una normalización propia se duplican contactos
   o no machean las conversaciones. Receta barata y robusta: guarda E.164
   canónico y matchea por los últimos 10 dígitos.
2. **Deduplicar mensajes entrantes.** Evolution reentrega webhooks cuando tu
   endpoint tarda o falla. El parser es puro: el mismo evento entra dos veces y
   produce dos mensajes idénticos. La dedup va en tu almacenamiento, con
   `message_id` como clave única (un índice único sirve mejor que un chequeo en
   memoria, que no sobrevive a varias réplicas).
3. **Decidir cuándo dar de alta un número.** `InstanceManager` expone crear
   instancia, pedir QR, consultar el estado de vinculación y cerrar sesión, pero
   quién puede dar de alta, cuántos números caben y qué hacer mientras el QR está
   en pantalla es del proyecto.
4. **Filtrar `from_me`.** Los mensajes que el negocio manda desde su propio
   celular llegan con `from_me=True` y se entregan igual. Un bot querrá
   ignorarlos; un espejo de conversaciones querrá reflejarlos como salientes.
   La decisión es del proyecto.

También conviene saber: **`parse_evolution` exige el campo `event`** en el
payload. Algunas configuraciones de Evolution entregan el `data` pelón; en ese
caso tu ruta debe etiquetar el evento antes de parsear. Es a propósito, para que
un `MESSAGES_UPDATE` no pueda colarse como mensaje.

## Asimetría honesta entre motores

No se finge simetría perfecta. El núcleo común (`send_text`, `send_document`, entrantes
normalizados) funciona igual en ambos. Lo específico vive en cada cliente:

| | Cloud API (WABA) | Evolution |
|---|---|---|
| Plantillas / ventana 24h | sí (`send_template`) | no |
| Catálogo de plantillas | sí (`list_templates`, requiere `waba_id`) | no |
| Enviar listas y botones | sí (`send_list`, `send_buttons`) | no |
| Recibir respuesta de listas y botones | sí | sí (normalizada a `interactive`) |
| Grupos | no | sí (`is_group`, autor en `from_number`) |
| Alta de números por API | no (se dan de alta en Meta) | sí (`InstanceManager`, QR) |
| Media generica | sí (`send_media`, por tipo real) | sí (`send_media`) |
| Nota de voz (PTT) | no distinguida | sí (`send_whatsapp_audio`) |
| Perfil del número | sí (`fetch_profile`, nombre verificado) | sí (`fetch_profile`) |
| Descarga de media | bytes (`get_media`) | base64 (`get_media_base64`) |
| Texto libre cuando quieras | solo dentro de 24h | sí |

## Manejo de errores (para tu cola)

- `ProviderAPIError` → 4xx permanente (plantilla mala, fuera de ventana): no reintentar.
- `ProviderTransportError` → fallo de transporte o respuesta transitoria
  (timeout/red/408/429/5xx). Las operaciones idempotentes pueden reintentarse; un
  envío con respuesta perdida queda ambiguo y no debe re-encolarse a ciegas.

`SendResult.accepted` significa que el proveedor acusó recibo **y** devolvió un
identificador de mensaje. Si vuelve `accepted=False` con `message_id=None`, el
envío quedó ambiguo: no hay con qué correlacionar el estado de entrega ni con qué
reconciliar un reintento. Revisa `raw` antes de decidir.

Los reintentos inmediatos con backoff se aplican por defecto solo a métodos HTTP
idempotentes. Los POST de envío no se reintentan automáticamente porque una respuesta
perdida después de que el proveedor aceptó el mensaje podría duplicarlo. Tu cola debe
reconciliar esos resultados ambiguos antes de volver a enviar.
