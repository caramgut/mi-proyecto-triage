import logging

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from auth.service import requerir_roles
from core.database import get_db
from routers.common import registrar_auditoria
from services.facturacion_ia import (
    crear_factura_manual,
    listar_facturas as mongo_listar_facturas,
    obtener_factura as mongo_obtener_factura,
    actualizar_estado_factura as mongo_actualizar_estado_factura,
    ping_mongo,
)

router = APIRouter(tags=["Facturación"])
log = logging.getLogger("facturacion")


class FacturaEstadoUpdate(BaseModel):
    estado_pago: str = Field(pattern="^(pendiente|pagada|anulada)$")


class FacturaCreate(BaseModel):
    paciente_id: int
    servicio: str = Field(min_length=2, max_length=80)
    valor: float = Field(ge=0)
    descripcion: str | None = Field(default=None, max_length=500)
    estado_pago: str = Field(default="pendiente", pattern="^(pendiente|pagada|anulada)$")
    numero_factura: str | None = Field(default=None, max_length=50)
    id_encuentro: int | None = Field(default=None, ge=1)


def _validar_paciente_y_encuentro(cur, data: FacturaCreate) -> None:
    cur.execute(
        """
        SELECT 1 FROM pacientes
        WHERE numero_documento_paciente=%s AND is_deleted=FALSE;
        """,
        (data.paciente_id,),
    )
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    if data.id_encuentro is not None:
        cur.execute(
            """
            SELECT 1 FROM encuentros
            WHERE id_encuentro=%s AND id_paciente=%s AND is_deleted=FALSE;
            """,
            (data.id_encuentro, data.paciente_id),
        )
        if not cur.fetchone():
            raise HTTPException(
                status_code=404,
                detail="El encuentro no existe o no pertenece al paciente",
            )


@router.get("/facturas/estado-mongo")
def estado_mongo(u=Depends(requerir_roles("Admin", "Contable"))):
    try:
        ping_mongo()
        return {"status": "ok", "base": "triaje", "coleccion": "facturas"}
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail="MongoDB no disponible") from exc


@router.post("/facturas", status_code=status.HTTP_201_CREATED)
def crear_factura(
    data: FacturaCreate,
    db=Depends(get_db),
    u=Depends(requerir_roles("Admin", "Contable")),
):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_paciente_y_encuentro(cur, data)
        try:
            factura = crear_factura_manual(
                paciente_id=data.paciente_id,
                servicio=data.servicio.strip(),
                valor=data.valor,
                usuario=u["numero_documento_usuario"],
                descripcion=(data.descripcion or "").strip() or None,
                estado_pago=data.estado_pago,
                numero_factura=(data.numero_factura or "").strip() or None,
                id_encuentro=data.id_encuentro,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PyMongoError as exc:
            raise HTTPException(status_code=503, detail="No fue posible guardar la factura en MongoDB") from exc

        registrar_auditoria(
            cur,
            "facturas",
            factura["id"],
            "CREAR",
            u["numero_documento_usuario"],
            nuevos={
                "id": factura["id"],
                "paciente_id": factura["paciente_id"],
                "servicio": factura["servicio"],
                "valor": factura["valor"],
                "estado_pago": factura["estado_pago"],
                "origen": factura["origen"],
            },
        )
        db.commit()
        return factura
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        cur.close()


@router.get("/facturas")
def listar_facturas(u=Depends(requerir_roles("Admin", "Contable"))):
    try:
        return mongo_listar_facturas()
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail="MongoDB no disponible") from exc


@router.get("/facturas/{id_factura}")
def ver_factura(id_factura: str, u=Depends(requerir_roles("Admin", "Contable"))):
    try:
        factura = mongo_obtener_factura(id_factura)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail="MongoDB no disponible") from exc
    if not factura:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    return factura


@router.patch("/facturas/{id_factura}/estado")
def actualizar_estado_factura(
    id_factura:str,
    data:FacturaEstadoUpdate,
    db=Depends(get_db),
    u=Depends(requerir_roles("Admin","Contable")),
):
    cur=db.cursor(cursor_factory=RealDictCursor)
    try:
        anterior=mongo_obtener_factura(id_factura)
        if not anterior:
            raise HTTPException(status_code=404,detail="Factura no encontrada")
        try:
            factura=mongo_actualizar_estado_factura(id_factura,data.estado_pago,u["numero_documento_usuario"])
        except PyMongoError as exc:
            raise HTTPException(status_code=503,detail="No fue posible actualizar la factura en MongoDB") from exc
        registrar_auditoria(
            cur,"facturas",id_factura,"EDITAR",u["numero_documento_usuario"],
            anteriores={"estado_pago":anterior.get("estado_pago")},
            nuevos={"estado_pago":factura.get("estado_pago"),"paciente_id":factura.get("paciente_id"),"origen":factura.get("origen")}
        )
        db.commit()
        return factura
    except HTTPException:
        db.rollback();raise
    except Exception:
        db.rollback();raise
    finally:
        cur.close()
