-- =====================================================================
-- 007 · IA: VARIABLES DE PRETRIAJE Y COHORTE SINTÉTICA (R07)
-- Idempotente: se puede ejecutar varias veces sin error.
-- =====================================================================

BEGIN;

-- Todo paciente queda marcado como real o sintético (R07).
ALTER TABLE pacientes
    ADD COLUMN IF NOT EXISTS origen VARCHAR(20) NOT NULL DEFAULT 'real';
ALTER TABLE pacientes DROP CONSTRAINT IF EXISTS chk_pacientes_origen;
ALTER TABLE pacientes ADD CONSTRAINT chk_pacientes_origen
    CHECK (origen IN ('real', 'sintetico'));

-- Datos del ingreso que usa el modelo y que el encuentro no tenía.
-- (El dolor ya existe: encuentros.dolor_escala.)
ALTER TABLE encuentros ADD COLUMN IF NOT EXISTS motivo_categoria VARCHAR(40);
ALTER TABLE encuentros ADD COLUMN IF NOT EXISTS llegada_ambulancia BOOLEAN;
ALTER TABLE encuentros ADD COLUMN IF NOT EXISTS lesion BOOLEAN;

ALTER TABLE encuentros DROP CONSTRAINT IF EXISTS chk_encuentros_motivo_categoria;
ALTER TABLE encuentros ADD CONSTRAINT chk_encuentros_motivo_categoria
    CHECK (motivo_categoria IS NULL OR motivo_categoria IN (
        'cardiovascular','respiratorio','digestivo','neurologico','conciencia_paro',
        'fiebre_general','trauma','musculoesqueletico','genitourinario_gineco',
        'psiquiatrico_sustancias','piel_alergia','orl_ojos_dental','otros'
    ));

-- Cada sintético queda ligado a su grupo (cluster) y a la fila real de la que salió.
CREATE TABLE IF NOT EXISTS ia_cohorte (
    numero_documento_paciente BIGINT PRIMARY KEY
        REFERENCES pacientes(numero_documento_paciente),

    cohorte VARCHAR(40) NOT NULL,

    id_cluster SMALLINT NOT NULL,

    grupo VARCHAR(80) NOT NULL,

    -- Nivel de triaje de enfermería de la fila base. Solo para evaluar:
    -- NO se copia al encuentro, porque el pretriaje lo debe proponer la IA.
    nivel_triaje_referencia SMALLINT
        CHECK (nivel_triaje_referencia BETWEEN 1 AND 5),

    fila_base INTEGER,

    u NUMERIC(4,3),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ia_cohorte_cluster ON ia_cohorte(id_cluster);

COMMIT;
