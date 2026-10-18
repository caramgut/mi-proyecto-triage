from fastapi import APIRouter,Depends
from psycopg2.extras import RealDictCursor

from auth.service import requerir_roles
from core.database import get_db

router=APIRouter()

@router.get("/admin/papelera-clinica",tags=["Administración"])
def papelera_clinica(db=Depends(get_db),u=Depends(requerir_roles("Admin"))):
    cur=db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM (
                SELECT 'antecedente' AS tipo, a.id_antecedente::text AS id_registro,
                       a.id_paciente, NULL::int AS id_encuentro, a.deleted_at, a.deleted_by,
                       COALESCE(a.tipo,'') || ': ' || LEFT(COALESCE(a.descripcion,''),120) AS resumen,
                       p.nombres || ' ' || p.apellidos AS paciente,
                       u.username AS eliminado_por
                FROM antecedentes a
                JOIN pacientes p ON p.numero_documento_paciente=a.id_paciente
                LEFT JOIN usuarios u ON u.numero_documento_usuario=a.deleted_by
                WHERE a.is_deleted=TRUE

                UNION ALL

                SELECT 'observacion', o.id_observacion::text, e.id_paciente, o.id_encuentro,
                       o.deleted_at,o.deleted_by,
                       COALESCE(o.nombre,o.tipo_observacion,'Observación') || ': ' ||
                       COALESCE(o.valor_numerico::text,o.valor_texto,'') ||
                       CASE WHEN o.unidad IS NOT NULL THEN ' ' || o.unidad ELSE '' END,
                       p.nombres || ' ' || p.apellidos, u.username
                FROM observaciones o
                JOIN encuentros e ON e.id_encuentro=o.id_encuentro
                JOIN pacientes p ON p.numero_documento_paciente=e.id_paciente
                LEFT JOIN usuarios u ON u.numero_documento_usuario=o.deleted_by
                WHERE o.is_deleted=TRUE

                UNION ALL

                SELECT 'diagnostico', d.id_diagnostico::text, e.id_paciente, d.id_encuentro,
                       d.deleted_at,d.deleted_by,LEFT(COALESCE(d.descripcion,''),140),
                       p.nombres || ' ' || p.apellidos, u.username
                FROM diagnosticos d
                JOIN encuentros e ON e.id_encuentro=d.id_encuentro
                JOIN pacientes p ON p.numero_documento_paciente=e.id_paciente
                LEFT JOIN usuarios u ON u.numero_documento_usuario=d.deleted_by
                WHERE d.is_deleted=TRUE

                UNION ALL

                SELECT 'nota', n.id_nota::text, e.id_paciente, n.id_encuentro,
                       n.deleted_at,n.deleted_by,
                       COALESCE(n.tipo_nota,'Nota') || ': ' || LEFT(COALESCE(n.contenido,''),120),
                       p.nombres || ' ' || p.apellidos, u.username
                FROM notas_clinicas n
                JOIN encuentros e ON e.id_encuentro=n.id_encuentro
                JOIN pacientes p ON p.numero_documento_paciente=e.id_paciente
                LEFT JOIN usuarios u ON u.numero_documento_usuario=n.deleted_by
                WHERE n.is_deleted=TRUE

                UNION ALL

                SELECT 'examen', x.id_examen::text, e.id_paciente, x.id_encuentro,
                       x.deleted_at,x.deleted_by,
                       COALESCE(x.nombre,'Examen'),
                       p.nombres || ' ' || p.apellidos, u.username
                FROM examenes x
                JOIN encuentros e ON e.id_encuentro=x.id_encuentro
                JOIN pacientes p ON p.numero_documento_paciente=e.id_paciente
                LEFT JOIN usuarios u ON u.numero_documento_usuario=x.deleted_by
                WHERE x.is_deleted=TRUE

                UNION ALL

                SELECT 'prescripcion', pr.id_prescripcion::text, e.id_paciente, pr.id_encuentro,
                       pr.deleted_at,pr.deleted_by,
                       COALESCE(m.nombre,pr.codigo_cum::text,'Prescripción') ||
                       CASE WHEN pr.dosis IS NOT NULL THEN ' · ' || pr.dosis ELSE '' END,
                       p.nombres || ' ' || p.apellidos, u.username
                FROM prescripciones pr
                JOIN encuentros e ON e.id_encuentro=pr.id_encuentro
                JOIN pacientes p ON p.numero_documento_paciente=e.id_paciente
                LEFT JOIN medicamentos m ON m.codigo_cum=pr.codigo_cum
                LEFT JOIN usuarios u ON u.numero_documento_usuario=pr.deleted_by
                WHERE pr.is_deleted=TRUE
            ) q
            ORDER BY deleted_at DESC NULLS LAST;
        """)
        return cur.fetchall()
    finally:
        cur.close()
