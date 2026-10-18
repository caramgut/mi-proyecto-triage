-- =====================================================================
-- 009 · Acción de auditoría REASIGNAR_MEDICO
-- Al desactivar un médico con encuentros activos, DELETE /usuarios/{doc}
-- registra REASIGNAR_MEDICO. Sin esta acción el CHECK de auditoria_cambios
-- la rechazaba y el endpoint respondía 500. Idempotente.
-- Aplicar: python scripts/ejecutar_migracion.py 009_auditoria_reasignar_medico.sql
-- =====================================================================
BEGIN;

ALTER TABLE auditoria_cambios
    DROP CONSTRAINT IF EXISTS chk_auditoria_cambios_accion;
ALTER TABLE auditoria_cambios
    DROP CONSTRAINT IF EXISTS auditoria_cambios_accion_check;

ALTER TABLE auditoria_cambios
    ADD CONSTRAINT chk_auditoria_cambios_accion
    CHECK (accion IN (
        'CREAR', 'EDITAR', 'ELIMINAR', 'RESTAURAR', 'DISPENSAR', 'ANULAR', 'FINALIZAR',
        'VINCULAR_CUENTA', 'REMITIR', 'ACEPTAR_REMISION', 'RECHAZAR_REMISION', 'RECIBIR_FHIR',
        'ANALIZAR_IA', 'APROBAR_REPORTE', 'RECHAZAR_REPORTE',
        'CREAR_ALERTA', 'RECONOCER_ALERTA', 'ESCALAR_ALERTA',
        'REASIGNAR_MEDICO'
    ));

COMMIT;
