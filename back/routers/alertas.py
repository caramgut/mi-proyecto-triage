# R20 · Alertas críticas con reconocimiento y escalamiento.
#
# 1. El análisis de IA (routers/ia_reportes.py) crea la alerta 'activa' cuando el modelo
#    supera el umbral de alerta o se activa la red de seguridad, y la publica en vivo.
# 2. Queda visible hasta que un médico o especialista la RECONOCE con una nota.
# 3. Si nadie la reconoce en ALERTA_ESCALAR_MINUTOS, un hilo de la API la escala al admin.
# 4. Creación, reconocimiento y escalamiento quedan en la auditoría.

import logging
import threading
import time

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel, Field

from auth.service import requerir_roles
from core.config import ALERTA_ESCALAR_MINUTOS, PG_CONNECTION_STRING
from core.database import get_db
from core.eventos import publicar, usuarios_por_rol
from routers.common import jsonable_row, registrar_auditoria

router = APIRouter(tags=["Alertas críticas (R20)"])
log = logging.getLogger("alertas")

TIPO_ALERTA = "alerta_critica"              # el tipo contiene "alerta" y "critica" (R20)
TIPO_ESCALADA = "alerta_critica_escalada"
TIPO_RECONOCIDA = "alerta_reconocida"


# ---------- Uso interno (lo llama el análisis de IA) ----------

def crear_alerta(cur, reporte: dict, destinatario: int | None, motivo: list[str], usuario: int) -> dict:
    """Inserta la alerta y su auditoría DENTRO de la transacción del análisis."""
    cur.execute("""
        INSERT INTO alertas(id_reporte, id_paciente, nivel, motivo, destinatario)
        VALUES (%s, %s, 'critico', %s, %s)
        RETURNING *;
    """, (reporte["id_reporte"], reporte["id_paciente"], Json(motivo), destinatario))
    alerta = cur.fetchone()
    registrar_auditoria(cur, "alertas", alerta["id_alerta"], "CREAR_ALERTA", usuario,
                        nuevos={"id_alerta": alerta["id_alerta"], "id_reporte": reporte["id_reporte"],
                                "id_paciente": reporte["id_paciente"], "nivel": alerta["nivel"],
                                "destinatario": destinatario, "motivo": motivo})
    return alerta


def _visible_sql(u: dict) -> tuple[str, list]:
    """Qué alertas ve cada rol. Paciente y Contable no llegan aquí (403 en requerir_roles)."""
    uid = u["numero_documento_usuario"]
    if u["rol"] == "Admin":
        return "TRUE", []
    if u["rol"] == "Medico":
        # Las suyas y las de encuentros sin médico responsable
        return "(a.destinatario = %s OR a.destinatario IS NULL)", [uid]
    return "a.destinatario = %s", [uid]


def contar_alertas_activas(cur, u: dict) -> int:
    """Contador 'alertas_activas' del endpoint de pendientes."""
    if u["rol"] not in ("Admin", "Medico", "Especialista"):
        return 0
    filtro, params = _visible_sql(u)
    if u["rol"] == "Admin":
        filtro = "a.escalada_at IS NOT NULL"          # al admin solo le corresponden las escaladas
    cur.execute(f"SELECT count(*) FROM alertas a WHERE a.estado = 'activa' AND EXISTS (SELECT 1 FROM reportes_ia r JOIN encuentros e ON e.id_encuentro=r.id_encuentro WHERE r.id_reporte=a.id_reporte AND e.estado <> 'finalizado' AND e.is_deleted=FALSE) AND {filtro};", params)
    fila = cur.fetchone()
    return int(fila["count"] if isinstance(fila, dict) else fila[0])


# ---------- Endpoints ----------

def _serializar(fila: dict) -> dict:
    a = jsonable_row(fila)
    a["id"] = a.pop("id_alerta")
    a["paciente_id"] = a.pop("id_paciente")
    a["reporte_id"] = a.pop("id_reporte")
    return a


@router.get("/alertas")
def listar_alertas(
    estado: str | None = Query(None, pattern="^(activa|reconocida)$"),
    db=Depends(get_db),
    u=Depends(requerir_roles("Admin", "Medico", "Especialista")),
):
    filtro, params = _visible_sql(u)
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(f"""
            SELECT a.*, p.nombres AS paciente_nombres, p.apellidos AS paciente_apellidos,
                   r.categoria, r.p_critico
            FROM alertas a
            JOIN pacientes p ON p.numero_documento_paciente = a.id_paciente
            JOIN reportes_ia r ON r.id_reporte = a.id_reporte
            WHERE {filtro} AND (a.estado <> 'activa' OR EXISTS (SELECT 1 FROM encuentros e WHERE e.id_encuentro=r.id_encuentro AND e.estado <> 'finalizado' AND e.is_deleted=FALSE)) AND (%s::text IS NULL OR a.estado = %s)
            ORDER BY (a.estado = 'activa') DESC, a.created_at DESC
            LIMIT 200;
        """, params + [estado, estado])
        return [_serializar(f) for f in cur.fetchall()]
    finally:
        cur.close()


class Reconocimiento(BaseModel):
    nota: str = Field(min_length=3, max_length=2000)


@router.patch("/alertas/{id_alerta}/reconocer")
def reconocer_alerta(
    id_alerta: int,
    data: Reconocimiento,
    db=Depends(get_db),
    u=Depends(requerir_roles("Medico", "Especialista")),
):
    uid = u["numero_documento_usuario"]
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM alertas WHERE id_alerta = %s FOR UPDATE;", (id_alerta,))
        anterior = cur.fetchone()
        if not anterior:
            raise HTTPException(status_code=404, detail="Alerta no encontrada")

        # La reconoce su destinatario. Si no tiene destinatario, o ya se escaló, cualquier médico.
        propia = anterior["destinatario"] == uid
        abierta = anterior["destinatario"] is None or anterior["escalada_at"] is not None
        if not propia and not (abierta and u["rol"] == "Medico"):
            raise HTTPException(status_code=403, detail="La alerta está asignada a otro clínico")
        if anterior["estado"] != "activa":
            raise HTTPException(status_code=409, detail="La alerta ya fue reconocida")

        cur.execute("""
            UPDATE alertas
            SET estado = 'reconocida', nota_reconocimiento = %s,
                reconocida_por = %s, reconocida_at = now()
            WHERE id_alerta = %s
            RETURNING *;
        """, (data.nota.strip(), uid, id_alerta))
        nueva = cur.fetchone()
        registrar_auditoria(cur, "alertas", id_alerta, "RECONOCER_ALERTA", uid,
                            anteriores={"estado": "activa"},
                            nuevos={"estado": "reconocida", "nota": nueva["nota_reconocimiento"],
                                    "id_paciente": nueva["id_paciente"], "id_reporte": nueva["id_reporte"]})
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()

    # Todos los que la estaban viendo deben quitar el aviso de su pantalla (también las otras
    # pestañas de quien la reconoció). Si se había escalado, también los admins.
    destinatarios = {uid}
    destinatarios |= {nueva["destinatario"]} if nueva["destinatario"] else set(usuarios_por_rol(db, "Medico"))
    if nueva["escalada_at"] is not None:
        destinatarios |= set(usuarios_por_rol(db, "Admin"))
    publicar(db, destinatarios, TIPO_RECONOCIDA,
             f"Alerta crítica #{id_alerta} reconocida: {nueva['nota_reconocimiento']}",
             paciente_id=nueva["id_paciente"], datos={"alerta_id": id_alerta, "reconocida_por": uid})
    return _serializar(nueva)


# ---------- Escalamiento automático ----------

def _escalar_vencidas() -> int:
    conn = psycopg2.connect(PG_CONNECTION_STRING)
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # SKIP LOCKED: si otra transacción está reconociendo la alerta, no la escalamos a la vez
        cur.execute("""
            SELECT a.*, p.nombres, p.apellidos
            FROM alertas a JOIN pacientes p ON p.numero_documento_paciente = a.id_paciente
            WHERE a.estado = 'activa' AND a.escalada_at IS NULL
              AND EXISTS (SELECT 1 FROM reportes_ia r JOIN encuentros e ON e.id_encuentro=r.id_encuentro WHERE r.id_reporte=a.id_reporte AND e.estado <> 'finalizado' AND e.is_deleted=FALSE)
              AND a.created_at < now() - make_interval(mins => %s)
            ORDER BY a.created_at
            FOR UPDATE OF a SKIP LOCKED;
        """, (ALERTA_ESCALAR_MINUTOS,))
        vencidas = cur.fetchall()
        for a in vencidas:
            cur.execute("UPDATE alertas SET escalada_at = now() WHERE id_alerta = %s;", (a["id_alerta"],))
            # Acción del SISTEMA: sin usuario, con origen distinto de 'API' (chk_auditoria_origen_usuario)
            cur.execute("""
                INSERT INTO auditoria_cambios(tabla_afectada, registro_id, accion, datos_nuevos,
                                              realizado_por, origen)
                VALUES ('alertas', %s, 'ESCALAR_ALERTA', %s, NULL, 'SISTEMA');
            """, (str(a["id_alerta"]), Json({"id_alerta": a["id_alerta"], "id_paciente": a["id_paciente"],
                                             "destinatario": a["destinatario"],
                                             "minutos_sin_reconocer": ALERTA_ESCALAR_MINUTOS})))
        conn.commit()

        admins = usuarios_por_rol(conn, "Admin")
        for a in vencidas:
            publicar(conn, admins, TIPO_ESCALADA,
                     f"Alerta crítica sin reconocer hace más de {ALERTA_ESCALAR_MINUTOS} min: "
                     f"{a['nombres']} {a['apellidos']}",
                     paciente_id=a["id_paciente"],
                     datos={"alerta_id": a["id_alerta"], "reporte_id": a["id_reporte"],
                            "destinatario_original": a["destinatario"]})
        return len(vencidas)
    finally:
        conn.close()


def _bucle_escalamiento():
    while True:
        try:
            n = _escalar_vencidas()
            if n:
                log.info("Alertas escaladas: %s", n)
        except Exception:
            log.exception("Fallo revisando alertas para escalar")
        time.sleep(30)


def iniciar_escalamiento():
    """Se llama una vez en el startup de main.py (la API corre con un solo worker)."""
    threading.Thread(target=_bucle_escalamiento, name="escalamiento-alertas", daemon=True).start()
