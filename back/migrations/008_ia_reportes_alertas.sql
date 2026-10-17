
BEGIN;

-- ---------------------------------------------------------------------
-- Lo que se envió EXACTAMENTE al modelo.
-- No tiene columnas de identidad: solo el seudónimo y las variables clínicas.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ia_payloads (
    id_payload BIGSERIAL PRIMARY KEY,

    seudonimo VARCHAR(64) NOT NULL,

    payload JSONB NOT NULL,

    enviado_por BIGINT NOT NULL
        REFERENCES usuarios(numero_documento_usuario),

    enviado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ia_payloads_seudonimo ON ia_payloads(seudonimo);


-- ---------------------------------------------------------------------
-- Reporte de IA. Nace 'pendiente'; solo el 'aprobado' entra a la historia.
-- El 'rechazado' NO se borra: queda como evidencia.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reportes_ia (
    id_reporte BIGSERIAL PRIMARY KEY,

    id_paciente BIGINT NOT NULL
        REFERENCES pacientes(numero_documento_paciente),

    id_encuentro INTEGER NOT NULL,

    id_payload BIGINT NOT NULL UNIQUE
        REFERENCES ia_payloads(id_payload),

    modelo_version VARCHAR(60) NOT NULL,

    -- Lo que verá el médico: crítico (niveles 1-2), medio (3), no crítico (4-5)
    categoria VARCHAR(20) NOT NULL
        CHECK (categoria IN ('critico', 'medio', 'no_critico')),

    p_critico NUMERIC(6,4) NOT NULL
        CHECK (p_critico BETWEEN 0 AND 1),

    -- Respuesta completa del modelo: probabilidades, factores, signos de alarma, grupo...
    resultado JSONB NOT NULL,

    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'aprobado', 'rechazado')),

    observaciones_clinico TEXT,

    revisado_por BIGINT
        REFERENCES usuarios(numero_documento_usuario),

    revisado_at TIMESTAMPTZ,

    solicitado_por BIGINT NOT NULL
        REFERENCES usuarios(numero_documento_usuario),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- El encuentro debe ser de ESTE paciente
    CONSTRAINT fk_reporte_ia_encuentro_paciente
        FOREIGN KEY (id_encuentro, id_paciente)
        REFERENCES encuentros(id_encuentro, id_paciente),

    -- Pendiente <=> nadie lo ha revisado
    CONSTRAINT chk_reporte_ia_revision
        CHECK ((estado = 'pendiente') = (revisado_por IS NULL AND revisado_at IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_reportes_ia_paciente ON reportes_ia(id_paciente);
CREATE INDEX IF NOT EXISTS idx_reportes_ia_pendientes ON reportes_ia(estado) WHERE estado = 'pendiente';


-- ---------------------------------------------------------------------
-- Alerta crítica. Activa hasta que un clínico la reconoce con una nota.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alertas (
    id_alerta BIGSERIAL PRIMARY KEY,

    id_reporte BIGINT NOT NULL UNIQUE
        REFERENCES reportes_ia(id_reporte),

    id_paciente BIGINT NOT NULL
        REFERENCES pacientes(numero_documento_paciente),

    nivel VARCHAR(20) NOT NULL DEFAULT 'critico',

    -- Por qué se disparó: "P(crítico) 98 % >= 38 %", "red de seguridad: SpO2 82 % < 88 %"...
    motivo JSONB NOT NULL,

    -- Clínico responsable que debe reconocerla.
    -- NULL = el encuentro no tiene médico responsable: la ven y la reconocen todos los médicos.
    destinatario BIGINT
        REFERENCES usuarios(numero_documento_usuario),

    estado VARCHAR(20) NOT NULL DEFAULT 'activa'
        CHECK (estado IN ('activa', 'reconocida')),

    nota_reconocimiento TEXT,

    reconocida_por BIGINT
        REFERENCES usuarios(numero_documento_usuario),

    reconocida_at TIMESTAMPTZ,

    -- Momento en que se escaló al admin por falta de reconocimiento
    escalada_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_alerta_reconocimiento
        CHECK (
            (estado = 'activa' AND reconocida_por IS NULL)
            OR (estado = 'reconocida' AND reconocida_por IS NOT NULL
                AND reconocida_at IS NOT NULL
                AND length(trim(nota_reconocimiento)) > 0)
        )
);

CREATE INDEX IF NOT EXISTS idx_alertas_destinatario ON alertas(destinatario, estado);
CREATE INDEX IF NOT EXISTS idx_alertas_activas ON alertas(created_at) WHERE estado = 'activa';


-- ---------------------------------------------------------------------
-- Auditoría: se conservan las 12 acciones que ya existen y se agregan las de IA.
-- ---------------------------------------------------------------------
ALTER TABLE auditoria_cambios
    DROP CONSTRAINT IF EXISTS chk_auditoria_cambios_accion;
-- El CHECK original del esquema (sin nombre propio) se reemplaza por el de arriba
ALTER TABLE auditoria_cambios
    DROP CONSTRAINT IF EXISTS auditoria_cambios_accion_check;

ALTER TABLE auditoria_cambios
    ADD CONSTRAINT chk_auditoria_cambios_accion
    CHECK (accion IN (
        'CREAR', 'EDITAR', 'ELIMINAR', 'RESTAURAR', 'DISPENSAR', 'ANULAR', 'FINALIZAR',
        'VINCULAR_CUENTA', 'REMITIR', 'ACEPTAR_REMISION', 'RECHAZAR_REMISION', 'RECIBIR_FHIR',
        'ANALIZAR_IA', 'APROBAR_REPORTE', 'RECHAZAR_REPORTE',
        'CREAR_ALERTA', 'RECONOCER_ALERTA', 'ESCALAR_ALERTA'
    ));

COMMIT;
