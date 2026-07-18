# wa-providers

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

Para Evolution: `parse_evolution(payload)`.

## Qué va en el paquete y qué en tu app

- **Paquete (framework-free):** clientes, esquemas normalizados, factory, parsers/verify de webhook, pooling + retry/backoff.
- **Tu app (por proyecto):** la ruta del webhook, guardar en tu DB, la UI, y —a escala— la cola + workers que consumen los envíos respetando los rate limits de Meta.

## Asimetría honesta entre motores

No se finge simetría perfecta. El núcleo común (`send_text`, `send_document`, entrantes
normalizados) funciona igual en ambos. Lo específico vive en cada cliente:

| | Cloud API (WABA) | Evolution |
|---|---|---|
| Plantillas / ventana 24h | sí (`send_template`) | no |
| Grupos | no | sí |
| Texto libre cuando quieras | solo dentro de 24h | sí |

## Manejo de errores (para tu cola)

- `ProviderAPIError` → 4xx permanente (plantilla mala, fuera de ventana): no reintentar.
- `ProviderTransportError` → fallo de transporte o respuesta transitoria
  (timeout/red/408/429/5xx). Las operaciones idempotentes pueden reintentarse; un
  envío con respuesta perdida queda ambiguo y no debe re-encolarse a ciegas.

Los reintentos inmediatos con backoff se aplican por defecto solo a métodos HTTP
idempotentes. Los POST de envío no se reintentan automáticamente porque una respuesta
perdida después de que el proveedor aceptó el mensaje podría duplicarlo. Tu cola debe
reconciliar esos resultados ambiguos antes de volver a enviar.
