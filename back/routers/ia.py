# R07: grupos (clusters) y cohorte sintética.
# El servicio ml genera las variables clínicas; la API les inventa una identidad
# y las guarda como pacientes, encuentros y observaciones de la historia clínica.

import random
from datetime import date

from fastapi import APIRouter, Depends
from psycopg2.extras import RealDictCursor, execute_values

from auth.service import requerir_roles
from core.database import get_db
from routers.common import registrar_auditoria
from services.ml_client import LOINC_SIGNOS, llamar_ml

router = APIRouter(tags=["IA"])

# Los sintéticos usan un rango de documentos reservado, fácil de reconocer.
DOCUMENTO_BASE = 9_900_000_000
HOY = date(2026, 10, 1)        # fecha fija: la misma cohorte para todo el equipo

NOMBRES = {
    "F": ["María", "Luisa", "Camila", "Valentina", "Paola", "Diana", "Carolina", "Natalia",
          "Andrea", "Laura", "Sandra", "Marcela", "Juliana", "Daniela", "Gloria", "Liliana"],
    "M": ["Juan", "Carlos", "Andrés", "Luis", "Jorge", "Camilo", "Sebastián", "Diego",
          "Felipe", "Óscar", "Julián", "Mateo", "Santiago", "Hernán", "Fabio", "Iván"],
}
APELLIDOS = ["Gómez", "Rodríguez", "Martínez", "López", "García", "Hernández", "Ramírez",
             "Torres", "Vargas", "Castro", "Ortiz", "Rojas", "Moreno", "Muñoz", "Cárdenas",
             "Valencia", "Escobar", "Cortés", "Quintero", "Arias", "Salazar", "Restrepo"]
MUNICIPIOS = ["Cali"] * 8 + ["Jamundí", "Palmira", "Yumbo", "Candelaria"]

MOTIVO_TEXTO = {
    "cardiovascular": "Dolor torácico / palpitaciones",
    "respiratorio": "Dificultad respiratoria",
    "digestivo": "Dolor abdominal / síntomas digestivos",
    "neurologico": "Cefalea, mareo o síntomas neurológicos",
    "conciencia_paro": "Alteración del estado de conciencia",
    "fiebre_general": "Fiebre / malestar general",
    "trauma": "Trauma o lesión",
    "musculoesqueletico": "Dolor musculoesquelético",
    "genitourinario_gineco": "Síntomas genitourinarios o ginecológicos",
    "psiquiatrico_sustancias": "Síntomas psiquiátricos o consumo de sustancias",
    "piel_alergia": "Lesión de piel / reacción alérgica",
    "orl_ojos_dental": "Síntoma de ojos, oídos, nariz, garganta o boca",
    "otros": "Otro motivo de consulta",
}


def _nacimiento(edad: float) -> date:
    return date(HOY.year - int(round(edad)), HOY.month, HOY.day)


@router.post("/ia/cohorte", status_code=201)
def crear_cohorte(db=Depends(get_db), u=Depends(requerir_roles("Admin"))):
    """Crea los pacientes sintéticos de R07. Si ya existen, no duplica nada."""
    datos = llamar_ml("POST", "/cohorte", timeout=120)
    admin = u["numero_documento_usuario"]

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Médicos activos: cada encuentro sintético queda a cargo de uno (por turnos).
        cur.execute("""
            SELECT u.numero_documento_usuario
            FROM usuarios u JOIN roles r ON r.id_rol = u.id_rol
            WHERE r.nombre = 'Medico' AND u.estado = TRUE AND u.is_deleted = FALSE
            ORDER BY u.numero_documento_usuario;
        """)
        medicos = [f["numero_documento_usuario"] for f in cur.fetchall()]

        # Los que ya existen no se duplican (se puede llamar varias veces).
        documentos = [DOCUMENTO_BASE + p["indice"] for p in datos["pacientes"]]
        cur.execute("SELECT numero_documento_paciente FROM pacientes WHERE numero_documento_paciente = ANY(%s);",
                    (documentos,))
        existentes = {f["numero_documento_paciente"] for f in cur.fetchall()}
        nuevos = [p for p in datos["pacientes"] if DOCUMENTO_BASE + p["indice"] not in existentes]
        creados = len(nuevos)

        if nuevos:
            # Todo se inserta EN LOTES (execute_values): unas pocas idas y vueltas a la base
            # en vez de una por fila. Con una base remota (Neon) es la diferencia entre
            # un par de segundos y varios minutos.
            pacientes, encuentros = [], []
            for i, p in enumerate(nuevos):
                documento = DOCUMENTO_BASE + p["indice"]
                rng = random.Random(documento)        # mismo paciente -> mismo nombre siempre
                pacientes.append((documento, rng.choice(NOMBRES[p["sexo"]]),
                                  f"{rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}",
                                  _nacimiento(p["edad"]), "male" if p["sexo"] == "M" else "female",
                                  rng.choice(MUNICIPIOS)))
                encuentros.append((documento, MOTIVO_TEXTO[p["motivo_categoria"]], p["motivo_categoria"],
                                   None if p["llegada_ambulancia"] is None else bool(p["llegada_ambulancia"]),
                                   None if p["lesion"] is None else bool(p["lesion"]),
                                   None if p["dolor_nrs"] is None else int(p["dolor_nrs"]),
                                   medicos[i % len(medicos)] if medicos else None, admin))

            execute_values(cur, """
                INSERT INTO pacientes(
                    numero_documento_paciente, nombres, apellidos, fecha_nacimiento,
                    genero_fhir, municipio_residencia, tipo_documento, zona_residencia, origen
                )
                VALUES %s;
            """, pacientes, template="(%s, %s, %s, %s, %s, %s, 'CC', 'urbana', 'sintetico')", page_size=500)

            filas = execute_values(cur, """
                INSERT INTO encuentros(
                    id_paciente, motivo_consulta, motivo_categoria, llegada_ambulancia,
                    lesion, dolor_escala, medico_responsable, creado_por, estado
                )
                VALUES %s
                RETURNING id_paciente, id_encuentro;
            """, encuentros, template="(%s, %s, %s, %s, %s, %s, %s, %s, 'en_triage')",
                page_size=500, fetch=True)
            encuentro_de = {f["id_paciente"]: f["id_encuentro"] for f in filas}

            observaciones = [
                (encuentro_de[DOCUMENTO_BASE + p["indice"]], loinc, nombre, p[variable], unidad, admin)
                for p in nuevos
                for variable, (loinc, nombre, unidad) in LOINC_SIGNOS.items()
                if p[variable] is not None                # a no todos se les mide todo
            ]
            execute_values(cur, """
                INSERT INTO observaciones(
                    id_encuentro, codigo_loinc, nombre, valor_numerico, unidad,
                    registrado_por, tipo_observacion
                )
                VALUES %s;
            """, observaciones, template="(%s, %s, %s, %s, %s, %s, 'signo_vital')", page_size=2000)

            execute_values(cur, """
                INSERT INTO ia_cohorte(
                    numero_documento_paciente, cohorte, id_cluster, grupo,
                    nivel_triaje_referencia, fila_base, u
                )
                VALUES %s;
            """, [(DOCUMENTO_BASE + p["indice"], datos["cohorte"], p["cluster"], p["grupo"],
                   p["nivel_triaje_referencia"], p["fila_base"], p["u"]) for p in nuevos], page_size=500)

        registrar_auditoria(cur, "ia_cohorte", datos["cohorte"], "CREAR", admin,
                            nuevos={"cohorte": datos["cohorte"], "creados": creados,
                                    "solicitados": datos["n"]})
        db.commit()
        return {"cohorte": datos["cohorte"], "solicitados": datos["n"], "creados": creados,
                "ya_existian": datos["n"] - creados}
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()


@router.get("/ia/clusters")
def ver_clusters(db=Depends(get_db), u=Depends(requerir_roles("Admin", "Medico", "Especialista"))):
    """R07: lista de grupos con descripción y conteos de pacientes reales (dataset) y sintéticos (base).

    Formato del contrato del tester: [{"cluster", "descripcion", "n_reales", "n_sinteticos", ...}]
    """
    resultado = llamar_ml("GET", "/clusters")

    cur = db.cursor()
    try:
        cur.execute("""
            SELECT c.id_cluster, count(*)
            FROM ia_cohorte c
            JOIN pacientes p ON p.numero_documento_paciente = c.numero_documento_paciente
            WHERE p.is_deleted = FALSE AND p.origen = 'sintetico'
            GROUP BY c.id_cluster;
        """)
        sinteticos = dict(cur.fetchall())
    finally:
        cur.close()

    return [{
        "cluster": g["cluster"],
        "nombre": g["nombre"],
        "descripcion": g["descripcion"],
        "n_reales": g["reales"],
        "n_sinteticos": int(sinteticos.get(g["cluster"], 0)),
        "pct_critico": g["pct_critico"],
        "mediana": g["mediana"],
    } for g in resultado["grupos"]]


@router.get("/ia/modelo")
def ver_modelo(u=Depends(requerir_roles("Admin", "Medico", "Especialista"))):
    """Ficha del modelo y del agrupamiento: versión, umbrales, métricas de prueba y criterio de k."""
    modelo = llamar_ml("GET", "/modelo")
    clusters = llamar_ml("GET", "/clusters")
    modelo["clusters"] = {k: clusters[k] for k in ("algoritmo", "k", "variables", "criterio_k")}
    return modelo
