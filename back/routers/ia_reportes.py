# R10 · Reporte de IA con aprobación clínica ("soft put") + R12 · payload seudonimizado.
#
# Flujo de POST /ia/analizar/{documento}:
#   historia clínica -> capa R12 (minimiza + seudonimiza) -> payload guardado -> servicio ml
#   -> reporte 'pendiente' -> (si es crítico) alerta R20 -> notificaciones en vivo
# El reporte NO entra a la historia clínica hasta que un médico o especialista lo aprueba.

import logging
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel, Field

from auth.service import requerir_roles
from core.database import get_db
from core.eventos import publicar, usuarios_por_rol
from routers.alertas import TIPO_ALERTA, crear_alerta
from routers.common import (exigir_especialista_remitido, jsonable_row, obtener_encuentro,
                            registrar_auditoria)
from routers.ia import MOTIVO_TEXTO
from services.ml_client import LOINC_SIGNOS, llamar_ml
from services.seudonimizacion import construir_payload, leer_variables

# R19 · Al aprobar, se crea sola la factura en MongoDB (módulo de contabilidad, R09).
# Cuando exista services/facturacion_ia.py con facturar_reporte_ia(...), se usa automáticamente.
try:
    from services.facturacion_ia import facturar_reporte_ia
except ImportError:
    facturar_reporte_ia = None

router = APIRouter(tags=["IA · reportes (R10, R12)"])
log = logging.getLogger("ia_reportes")

CATEGORIA_TEXTO = {"critico": "crítico (niveles 1-2)", "medio": "medio (nivel 3)",
                   "no_critico": "no crítico (niveles 4-5)"}
Motivo = Literal[tuple(MOTIVO_TEXTO)]


# ---------- Reglas de acceso ----------

def exigir_acceso_clinico(cur, encuentro: dict, u: dict):
    """Médico: sus encuentros o los que no tienen responsable. Especialista: con remisión aceptada."""
    if u["rol"] == "Medico" and encuentro["medico_responsable"] not in (None, u["numero_documento_usuario"]):
        raise HTTPException(status_code=403, detail="El encuentro está asignado a otro médico")
    if u["rol"] == "Especialista":
        exigir_especialista_remitido(cur, encuentro["id_paciente"], u, encuentro["id_encuentro"], True)


def _visible_sql(u: dict) -> tuple[str, list]:
    """Qué reportes ve cada rol en las listas (mismas reglas que exigir_acceso_clinico)."""
    uid = u["numero_documento_usuario"]
    if u["rol"] == "Admin":
        return "TRUE", []
    if u["rol"] == "Medico":
        return "(e.medico_responsable = %s OR e.medico_responsable IS NULL)", [uid]
    return """EXISTS (SELECT 1 FROM remisiones rm
                      WHERE rm.id_paciente = r.id_paciente AND rm.especialista_destino = %s
                        AND rm.estado = 'aceptada' AND rm.is_deleted = FALSE)""", [uid]


def contar_reportes_por_revisar(cur, u: dict) -> int:
    """Contador 'reportes_por_revisar' del endpoint de pendientes (solo quien puede aprobar)."""
    if u["rol"] not in ("Medico", "Especialista"):
        return 0
    filtro, params = _visible_sql(u)
    cur.execute(f"""
        SELECT count(*) FROM reportes_ia r JOIN encuentros e ON e.id_encuentro = r.id_encuentro
        WHERE r.estado = 'pendiente' AND {filtro};
    """, params)
    fila = cur.fetchone()
    return int(fila["count"] if isinstance(fila, dict) else fila[0])


def _clinicos_a_notificar(db, encuentro: dict, u: dict) -> tuple[int | None, list[int]]:
    """(destinatario de la alerta, a quiénes notificar)."""
    if encuentro["medico_responsable"]:
        return encuentro["medico_responsable"], [encuentro["medico_responsable"]]
    if u["rol"] in ("Medico", "Especialista"):
        return u["numero_documento_usuario"], [u["numero_documento_usuario"]]
    # Encuentro sin responsable analizado por un admin: les llega a todos los médicos
    return None, usuarios_por_rol(db, "Medico")


def _serializar(r: dict) -> dict:
    d = jsonable_row(r)
    d["id"] = d["id_reporte"]
    d["paciente_id"] = d["id_paciente"]
    return d


def _obtener_reporte(cur, id_reporte: int, u: dict, bloquear: bool = False) -> dict:
    cur.execute(f"""
        SELECT r.*, e.medico_responsable
        FROM reportes_ia r JOIN encuentros e ON e.id_encuentro = r.id_encuentro
        WHERE r.id_reporte = %s {"FOR UPDATE OF r" if bloquear else ""};
    """, (id_reporte,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    exigir_acceso_clinico(cur, {"id_paciente": r["id_paciente"], "id_encuentro": r["id_encuentro"],
                                "medico_responsable": r["medico_responsable"]}, u)
    return r


# ---------- Análisis ----------

class SignosEntrada(BaseModel):
    fc: float | None = Field(default=None, ge=20, le=250)
    fr: float | None = Field(default=None, ge=4, le=80)
    pas: float | None = Field(default=None, ge=40, le=300)
    pad: float | None = Field(default=None, ge=20, le=200)
    temp_c: float | None = Field(default=None, ge=30, le=44)
    spo2: float | None = Field(default=None, ge=50, le=100)
    dolor_nrs: int | None = Field(default=None, ge=0, le=10)


class SolicitudAnalisis(BaseModel):
    """Todo opcional: sin cuerpo, se analiza con lo que ya está en la historia clínica."""
    id_encuentro: int | None = None
    signos: SignosEntrada | None = None
    motivo_categoria: Motivo | None = None
    llegada_ambulancia: bool | None = None
    lesion: bool | None = None


def _encuentro_para_analizar(cur, paciente: dict, datos: SolicitudAnalisis, u: dict) -> dict:
    documento = paciente["numero_documento_paciente"]
    if datos.id_encuentro is not None:
        enc = obtener_encuentro(cur, datos.id_encuentro, False)
        if not enc or enc["id_paciente"] != documento:
            raise HTTPException(status_code=404, detail="Encuentro no encontrado para este paciente")
        return enc

    cur.execute("""
        SELECT * FROM encuentros
        WHERE id_paciente = %s AND is_deleted = FALSE AND estado <> 'finalizado'
        ORDER BY fecha_hora_ingreso DESC LIMIT 1;
    """, (documento,))
    enc = cur.fetchone()
    if enc:
        return dict(enc)

    if datos.signos is None:
        raise HTTPException(status_code=422,
                            detail="El paciente no tiene un encuentro activo con signos vitales para analizar")

    # Sin encuentro activo pero con signos en la solicitud: se abre el encuentro de pretriaje
    motivo = datos.motivo_categoria or "otros"
    cur.execute("""
        INSERT INTO encuentros(id_paciente, motivo_consulta, motivo_categoria, llegada_ambulancia, lesion,
                               dolor_escala, medico_responsable, creado_por, estado)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'en_triage')
        RETURNING *;
    """, (documento, MOTIVO_TEXTO[motivo], motivo, datos.llegada_ambulancia, datos.lesion,
          datos.signos.dolor_nrs, u["numero_documento_usuario"] if u["rol"] == "Medico" else None,
          u["numero_documento_usuario"]))
    enc = cur.fetchone()
    registrar_auditoria(cur, "encuentros", enc["id_encuentro"], "CREAR", u["numero_documento_usuario"], nuevos=enc)
    return dict(enc)


def _registrar_datos_de_ingreso(cur, enc: dict, datos: SolicitudAnalisis, u: dict) -> dict:
    """Guarda en la historia lo que vino en la solicitud (signos y datos del ingreso)."""
    uid = u["numero_documento_usuario"]
    if enc["estado"] == "finalizado" and (datos.signos or datos.motivo_categoria or
                                          datos.llegada_ambulancia is not None or datos.lesion is not None):
        raise HTTPException(status_code=409, detail="El encuentro está finalizado")

    cambios = {}
    if datos.motivo_categoria is not None:
        cambios["motivo_categoria"] = datos.motivo_categoria
    if datos.llegada_ambulancia is not None:
        cambios["llegada_ambulancia"] = datos.llegada_ambulancia
    if datos.lesion is not None:
        cambios["lesion"] = datos.lesion
    if datos.signos and datos.signos.dolor_nrs is not None:
        cambios["dolor_escala"] = datos.signos.dolor_nrs
    cambios = {k: v for k, v in cambios.items() if enc.get(k) != v}
    if cambios:
        sets = ", ".join(f"{k} = %s" for k in cambios)
        cur.execute(f"UPDATE encuentros SET {sets}, updated_at = now() WHERE id_encuentro = %s RETURNING *;",
                    [*cambios.values(), enc["id_encuentro"]])
        nuevo = dict(cur.fetchone())
        registrar_auditoria(cur, "encuentros", enc["id_encuentro"], "EDITAR", uid,
                            anteriores={k: enc.get(k) for k in cambios}, nuevos=cambios)
        enc = nuevo

    if datos.signos:
        signos = datos.signos.model_dump()
        for variable, (loinc, nombre, unidad) in LOINC_SIGNOS.items():
            if signos.get(variable) is None:
                continue
            cur.execute("""
                INSERT INTO observaciones(id_encuentro, tipo_observacion, codigo_loinc, nombre,
                                          valor_numerico, unidad, registrado_por)
                VALUES (%s, 'signo_vital', %s, %s, %s, %s, %s)
                RETURNING *;
            """, (enc["id_encuentro"], loinc, nombre, signos[variable], unidad, uid))
            obs = cur.fetchone()
            registrar_auditoria(cur, "observaciones", obs["id_observacion"], "CREAR", uid, nuevos=obs)
    return enc


@router.post("/ia/analizar/{documento}", status_code=201)
def analizar(
    documento: int,
    datos: SolicitudAnalisis | None = Body(default=None),
    db=Depends(get_db),
    u=Depends(requerir_roles("Admin", "Medico", "Especialista")),
):
    datos = datos or SolicitudAnalisis()
    uid = u["numero_documento_usuario"]
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM pacientes WHERE numero_documento_paciente = %s AND is_deleted = FALSE;",
                    (documento,))
        paciente = cur.fetchone()
        if not paciente:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")

        enc = _encuentro_para_analizar(cur, paciente, datos, u)
        exigir_acceso_clinico(cur, enc, u)
        enc = _registrar_datos_de_ingreso(cur, enc, datos, u)

        # R12: minimizar + seudonimizar, y guardar EXACTAMENTE lo que se envía
        variables, avisos = leer_variables(cur, paciente, enc)
        payload = construir_payload(documento, variables)
        cur.execute("""
            INSERT INTO ia_payloads(seudonimo, payload, enviado_por)
            VALUES (%s, %s, %s) RETURNING id_payload;
        """, (payload["seudonimo"], Json(payload), uid))
        id_payload = cur.fetchone()["id_payload"]

        resultado = llamar_ml("POST", "/predecir", json=payload)
        resultado["avisos"] = avisos

        cur.execute("""
            INSERT INTO reportes_ia(id_paciente, id_encuentro, id_payload, modelo_version, categoria,
                                    p_critico, resultado, solicitado_por)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *;
        """, (documento, enc["id_encuentro"], id_payload, resultado["modelo_version"], resultado["categoria"],
              resultado["p_critico"], Json(resultado), uid))
        reporte = cur.fetchone()
        registrar_auditoria(cur, "reportes_ia", reporte["id_reporte"], "ANALIZAR_IA", uid,
                            nuevos={"id_reporte": reporte["id_reporte"], "id_paciente": documento,
                                    "id_encuentro": enc["id_encuentro"], "id_payload": id_payload,
                                    "modelo_version": reporte["modelo_version"],
                                    "categoria": reporte["categoria"], "p_critico": reporte["p_critico"],
                                    "estado": "pendiente"})

        destinatario, notificar = _clinicos_a_notificar(db, enc, u)
        alerta = None
        if resultado["alerta_critica"]:
            alerta = crear_alerta(cur, reporte, destinatario, resultado["motivo_alerta"], uid)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()

    # Notificaciones DESPUÉS del commit (publicar hace su propio commit y nunca falla)
    nombre = f"{paciente['nombres']} {paciente['apellidos']}"
    publicar(db, notificar, "reporte_ia_pendiente",
             f"Pretriaje de IA por revisar: {nombre} · {CATEGORIA_TEXTO[reporte['categoria']]}",
             paciente_id=documento,
             datos={"reporte_id": reporte["id_reporte"], "categoria": reporte["categoria"]})
    if alerta:
        publicar(db, notificar, TIPO_ALERTA,
                 f"ALERTA CRÍTICA: {nombre} · " + "; ".join(resultado["motivo_alerta"]),
                 paciente_id=documento,
                 datos={"alerta_id": alerta["id_alerta"], "reporte_id": reporte["id_reporte"],
                        "nivel": alerta["nivel"], "motivo": resultado["motivo_alerta"]})

    return {
        "id": reporte["id_reporte"],
        "estado": reporte["estado"],
        "paciente_id": documento,
        "id_encuentro": enc["id_encuentro"],
        "categoria": reporte["categoria"],
        "categoria_texto": CATEGORIA_TEXTO[reporte["categoria"]],
        "probabilidades": resultado["probabilidades"],
        "p_critico": resultado["p_critico"],
        "alerta": None if not alerta else {"id": alerta["id_alerta"], "estado": alerta["estado"],
                                          "motivo": resultado["motivo_alerta"]},
        "signos_alarma": resultado["signos_alarma"],
        "factores_suben": resultado["factores_suben"],
        "factores_bajan": resultado["factores_bajan"],
        "grupo": resultado.get("grupo"),
        "avisos": avisos,
        "modelo_version": resultado["modelo_version"],
    }


# ---------- Consultas ----------

@router.get("/ia/reportes")
def listar_reportes(
    estado: Literal["pendiente", "aprobado", "rechazado"] | None = "pendiente",
    db=Depends(get_db),
    u=Depends(requerir_roles("Admin", "Medico", "Especialista")),
):
    """Bandeja de revisión: por defecto, los pendientes que le tocan al usuario."""
    filtro, params = _visible_sql(u)
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(f"""
            SELECT r.*, p.nombres AS paciente_nombres, p.apellidos AS paciente_apellidos,
                   EXISTS (SELECT 1 FROM alertas a WHERE a.id_reporte = r.id_reporte) AS con_alerta
            FROM reportes_ia r
            JOIN encuentros e ON e.id_encuentro = r.id_encuentro
            JOIN pacientes p ON p.numero_documento_paciente = r.id_paciente
            WHERE {filtro} AND (%s::text IS NULL OR r.estado = %s)
            ORDER BY r.created_at DESC LIMIT 200;
        """, params + [estado, estado])
        return [_serializar(f) for f in cur.fetchall()]
    finally:
        cur.close()


@router.get("/ia/pacientes/{documento}/reportes")
def reportes_del_paciente(documento: int, db=Depends(get_db),
                          u=Depends(requerir_roles("Admin", "Medico", "Especialista"))):
    """Todos los reportes del paciente (pendientes, aprobados y rechazados), para la ficha."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if u["rol"] == "Especialista":
            exigir_especialista_remitido(cur, documento, u, None, True)
        cur.execute("""
            SELECT r.*, a.id_alerta, a.estado AS estado_alerta
            FROM reportes_ia r LEFT JOIN alertas a ON a.id_reporte = r.id_reporte
            WHERE r.id_paciente = %s ORDER BY r.created_at DESC;
        """, (documento,))
        return [_serializar(f) for f in cur.fetchall()]
    finally:
        cur.close()


@router.get("/ia/reportes/{id_reporte}")
def ver_reporte(id_reporte: int, db=Depends(get_db),
                u=Depends(requerir_roles("Admin", "Medico", "Especialista"))):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        r = _obtener_reporte(cur, id_reporte, u)
        cur.execute("SELECT id_alerta, estado, nota_reconocimiento FROM alertas WHERE id_reporte = %s;",
                    (id_reporte,))
        d = _serializar(r)
        d["alerta"] = jsonable_row(cur.fetchone())
        return d
    finally:
        cur.close()


@router.get("/ia/reportes/{id_reporte}/payload")
def ver_payload(id_reporte: int, db=Depends(get_db),
                u=Depends(requerir_roles("Admin", "Medico", "Especialista"))):
    """R12: el JSON exacto que se envió al modelo para este reporte."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _obtener_reporte(cur, id_reporte, u)
        cur.execute("""
            SELECT p.id_payload, p.payload, p.enviado_at
            FROM ia_payloads p JOIN reportes_ia r ON r.id_payload = p.id_payload
            WHERE r.id_reporte = %s;
        """, (id_reporte,))
        f = cur.fetchone()
        return {"payload": f["payload"], "id_payload": f["id_payload"], "enviado_at": f["enviado_at"].isoformat()}
    finally:
        cur.close()


# ---------- Aprobación clínica ----------

class Revision(BaseModel):
    observaciones: str | None = Field(default=None, max_length=2000)


def _revisar(id_reporte: int, nuevo_estado: str, accion: str, data: Revision | None, db, u: dict) -> dict:
    uid = u["numero_documento_usuario"]
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        r = _obtener_reporte(cur, id_reporte, u, bloquear=True)
        if r["estado"] != "pendiente":
            raise HTTPException(status_code=409, detail=f"El reporte ya fue {r['estado']}")
        obs = (data.observaciones or "").strip() or None if data else None
        cur.execute("""
            UPDATE reportes_ia
            SET estado = %s, observaciones_clinico = %s, revisado_por = %s, revisado_at = now()
            WHERE id_reporte = %s RETURNING *;
        """, (nuevo_estado, obs, uid, id_reporte))
        nuevo = cur.fetchone()
        registrar_auditoria(cur, "reportes_ia", id_reporte, accion, uid,
                            anteriores={"estado": "pendiente"},
                            nuevos={"estado": nuevo_estado, "observaciones": obs,
                                    "id_paciente": nuevo["id_paciente"], "categoria": nuevo["categoria"]})
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()
    return _serializar(nuevo)


@router.patch("/ia/reportes/{id_reporte}/aprobar")
def aprobar_reporte(id_reporte: int, data: Revision | None = Body(default=None), db=Depends(get_db),
                    u=Depends(requerir_roles("Medico", "Especialista"))):
    reporte = _revisar(id_reporte, "aprobado", "APROBAR_REPORTE", data, db, u)
    reporte["factura"] = None
    if facturar_reporte_ia:
        # R19: la factura se crea sola. Si MongoDB falla, el reporte ya quedó aprobado y se registra el error.
        try:
            reporte["factura"] = facturar_reporte_ia(paciente_id=reporte["id_paciente"],
                                                     reporte_id=reporte["id_reporte"],
                                                     usuario=u["numero_documento_usuario"])
        except Exception:
            log.exception("No se pudo crear la factura del reporte %s", id_reporte)
    return reporte


@router.patch("/ia/reportes/{id_reporte}/rechazar")
def rechazar_reporte(id_reporte: int, data: Revision | None = Body(default=None), db=Depends(get_db),
                     u=Depends(requerir_roles("Medico", "Especialista"))):
    return _revisar(id_reporte, "rechazado", "RECHAZAR_REPORTE", data, db, u)
