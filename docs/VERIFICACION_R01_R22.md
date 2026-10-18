# Verificación de cierre R01–R22

Este archivo resume lo verificable estáticamente en el repositorio. Los requisitos que dependen de servicios externos o datos persistidos deben probarse con el stack levantado.

| Req. | Estado de código/configuración | Observación |
|---|---|---|
| R01 | OK | Cinco roles y control por rol. |
| R02 | OK | Bloqueo a 3 intentos, desbloqueo Admin, auditoría/notificación. |
| R03 | OK con verificación Git | JWT/RBAC/hash/CORS/headers/rate limit presentes. Ejecutar `git ls-files` y confirmar que secretos no estén rastreados. |
| R04 | OK configuración | `cloudflared` está dentro de Compose. La disponibilidad de la URL se prueba en vivo. |
| R05 | OK configuración | Compose contiene API, PostgreSQL para HAPI, MongoDB, FHIR, PACS, ML, frontend y cloudflared. La aplicación clínica usa Neon PostgreSQL externo. |
| R06 | PENDIENTE DATASET | PACS/API existen, pero falta seleccionar, documentar y cargar el dataset público real definitivo. |
| R07 | OK | Dataset tabular, k-means k=5 y sintéticos por cluster implementados; completar URL/licencia documental si faltan. |
| R08 | OK | Remisión, bandeja, aceptación, permisos y auditoría. |
| R09 | OK | MongoDB, permisos y factura IA automática. |
| R10 | OK | Reporte pendiente, aprobación/rechazo y filtrado de historia. |
| R11 | OK | PDF e IA aprobada únicamente. |
| R12 | OK | Payload minimizado/seudonimizado y trazable. |
| R13 | OK | Auditoría integral implementada. |
| R14 | OK | Médico puede soft-delete solo pacientes creados por él; Admin restaura. |
| R15 | OK código/configuración | FHIR R4 integrado; probar recursos en vivo. |
| R16 | OK | SPA con lista de pacientes, ficha, PACS, IA, remisiones, contabilidad, admin y notificaciones. |
| R17 | OK | SSE autenticado y `proxy_buffering off`. |
| R18 | OK | Bandeja persistente y `/pendientes`. |
| R19 | OK | Cuatro reacciones automáticas implementadas. |
| R20 | OK | Alertas, reconocimiento, auditoría y escalamiento. |
| R21 | OK configuración | HAPI expuesto por `/fhir/`; Subscription rest-hook reacciona a Observation. Probar en vivo. |
| R22 | OK documental salvo dataset | README actualizado con arquitectura, eventos, despliegue, normativa, métricas y sesgo. |

## Pendientes que impiden afirmar 100 % todavía

1. R06: elegir un dataset público real de imágenes, registrar nombre/URL/licencia/cantidad/pertinencia en `docs/DATASETS.md`, cargar al menos una imagen en Orthanc y confirmar que `GET /pacientes/{documento}/imagenes` devuelve y permite descargarla.
2. R03: confirmar en el repositorio Git real que `.env` y `back/pass.env` no están rastreados.
3. R04/R15/R21: ejecutar la prueba viva con la URL pública vigente.
4. `tester.yaml`: pegar la URL vigente del Quick Tunnel antes de la evaluación.


## Cierre R14 y R20 en frontend

- **R14:** el menú Médico > Pacientes muestra `Desactivar ficha` únicamente en pacientes creados por ese mismo médico. La operación es soft delete. El Admin dispone de la vista `Pacientes eliminados` y puede restaurar la ficha.
- **R20:** las alertas críticas permanecen visibles para el clínico hasta su reconocimiento. Si vencen sin reconocer, el backend las escala automáticamente y el Admin dispone de `Alertas escaladas`, además de recibir el evento en vivo. El escalamiento no tiene botón manual, porque debe ser consecuencia automática del tiempo.
