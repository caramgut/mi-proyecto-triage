# Contabilidad en MongoDB (R09)

La facturación del Corte 2 se persiste en **MongoDB**, base `triaje`, colección `facturas`.
PostgreSQL conserva la información clínica y la auditoría; MongoDB conserva los documentos contables.

## Estructura del documento

```json
{
  "_id": "ObjectId",
  "paciente_id": 1187405367,
  "id_encuentro": 8,
  "reporte_id": 12,
  "numero_factura": "IA-000012",
  "servicio": "analisis_ia",
  "descripcion": "Análisis de apoyo al triaje con IA aprobado por el clínico",
  "valor": 45000,
  "fecha": "2026-10-16T20:00:00+00:00",
  "estado_pago": "pendiente",
  "origen": "automatica",
  "creada_por": 1197694986
}
```

Campos obligatorios para R09: `paciente_id`, `servicio`, `valor`, `fecha` y `estado_pago`.
Las facturas de IA agregan `reporte_id`, que es único, para impedir doble facturación del mismo reporte. `numero_factura` también es único cuando existe. Las facturas manuales llevan `origen = "manual"` y las de IA `origen = "automatica"`.

## Permisos

- `Admin`: crea, lista, consulta y actualiza el estado de pago de las facturas.
- `Contable`: crea, lista, consulta y actualiza el estado de pago de las facturas.
- `Medico`, `Especialista` y `Paciente`: reciben 403 en los endpoints contables.

## Endpoints

- `GET /facturas/estado-mongo`: verifica conectividad con MongoDB.
- `POST /facturas`: crea una factura manual.
- `GET /facturas`: lista las facturas Mongo.
- `GET /facturas/{id}`: consulta una factura por ObjectId.
- `PATCH /facturas/{id}/estado`: cambia `estado_pago` (404 si la factura no existe; 503 si MongoDB no responde).

Ejemplo de factura manual:

```json
{
  "paciente_id": 1187405367,
  "servicio": "consulta",
  "valor": 65000,
  "descripcion": "Consulta de urgencias",
  "estado_pago": "pendiente",
  "id_encuentro": 8
}
```

## Flujo automático de IA (R19)

1. El profesional ejecuta el análisis y se crea un reporte IA `pendiente`.
2. El profesional aprueba el reporte.
3. `facturar_reporte_ia()` crea automáticamente una factura Mongo con `servicio=analisis_ia` y `reporte_id`.
4. La creación se registra en la auditoría PostgreSQL (`tabla_afectada=facturas`, `accion=CREAR`).
5. Se publica `factura_ia_creada` a los usuarios Contable/Admin; si la vista de facturación está abierta se actualiza sin recargar.
6. El índice único sobre `reporte_id` evita duplicar una factura IA.

## Conexión

El contenedor `api` recibe desde Compose:

```text
MONGO_CONNECTION_STRING=mongodb://mongodb:27017/triaje
```

No se versionan credenciales reales. Los secretos permanecen en `.env` local.

## Gestión del estado de pago

El rol `Contable` y el `Admin` pueden cambiar `estado_pago` entre `pendiente`, `pagada` y `anulada` con `PATCH /facturas/{id}/estado`. La edición modifica únicamente el estado contable; no cambia el `reporte_id`, el origen automático/manual, el valor ni la historia clínica.

Cada cambio guarda en la factura quién lo hizo y cuándo (`actualizada_por`, `updated_at`) y queda en la auditoría de PostgreSQL (`tabla_afectada = facturas`, `accion = EDITAR`, con el estado anterior y el nuevo).

## Documentos relacionados

[`EVENTOS.md`](EVENTOS.md) (`factura_ia_creada`) · [`MODELO.md`](MODELO.md) (reporte de IA que genera la factura) · [`LEYES.md`](LEYES.md) · [README](../README.md)
